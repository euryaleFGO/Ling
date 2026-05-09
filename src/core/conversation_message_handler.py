# -*- coding: utf-8 -*-
"""
Message handling for AsyncConversationManager.

Covers: LLM streaming, ASR listening / recognition, text-input submission,
streaming-text merging, and emotion-tag stripping.  Designed to be mixed into
``AsyncConversationManager`` via multiple inheritance.
"""

import asyncio
import logging
import re
import threading
import time
from collections.abc import AsyncIterator
from typing import Optional, TYPE_CHECKING

import numpy as np

from core.log import log
from core.performance_metrics import ASRMetrics

if TYPE_CHECKING:
    from core.conversation_manager_async import AsyncConversationManager

logger = logging.getLogger(__name__)

_EMOTION_PATTERN = re.compile(
    r'\[(joy|anger|sadness|surprise|neutral|shy|think|fear|cry)\]',
    re.IGNORECASE,
)


# ============================================================
#  Mixin
# ============================================================

class MessageHandlerMixin:
    """Message-level helpers: stream, listen, merge, emotion-tag stripping.

    All methods reference ``self`` attributes that must exist on the final
    ``AsyncConversationManager`` instance.
    """

    # -- Agent streaming ----------------------------------------------------

    async def _stream_agent_reply(
        self: "AsyncConversationManager", user_text: str
    ) -> AsyncIterator[str]:
        """Wrap the synchronous agent streaming generator in an async iterator."""
        if not self._agent:
            yield "Sorry, AI service is not initialised."
            return

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        exception_holder = [None]
        loop = asyncio.get_running_loop()
        cancel_event = threading.Event()

        def _sync_generator():
            try:
                for chunk in self._agent.chat(user_text, stream=True):
                    if cancel_event.is_set():
                        log.info("[Agent] streaming cancelled by interrupt")
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as e:
                log.error(f"Agent streaming error: {e}")
                exception_holder[0] = e
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        task = asyncio.create_task(asyncio.to_thread(_sync_generator))
        self._current_stream_task = task

        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    if exception_holder[0]:
                        raise exception_holder[0]
                    break
                yield chunk
        except asyncio.CancelledError:
            cancel_event.set()
            # 等待后台线程完成（最多 2 秒）
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            raise
        finally:
            self._current_stream_task = None

    # -- ASR / input --------------------------------------------------------

    async def _listen_and_recognize_async(
        self: "AsyncConversationManager",
    ) -> Optional[str]:
        """Asynchronously listen and recognise user speech (or text)."""
        queue = self._user_text_queue
        if queue is not None:
            try:
                return await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                return None

        if self._asr:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._listen_with_asr),
                    timeout=120.0,
                )
            except asyncio.TimeoutError:
                log.warning("[ASR] listen timeout (120s), forcing return")
                if hasattr(self, '_asr_cancel'):
                    self._asr_cancel.set()
                return None
            except asyncio.CancelledError:
                if hasattr(self, '_asr_cancel'):
                    self._asr_cancel.set()
                raise
            except Exception as e:
                log.warn(f"ASR recognition error: {e}")
                return await asyncio.to_thread(self._listen_with_text)
        return await asyncio.to_thread(self._listen_with_text)

    def _listen_with_asr(self: "AsyncConversationManager") -> Optional[str]:
        """Listen via ASR (synchronous, called from ``asyncio.to_thread``)."""
        # 清空上一轮的声纹嵌入
        self._last_speaker_embedding = None

        asr_type = type(self._asr).__name__
        log.info(f"Please speak ... [ASR: {asr_type}]")

        t_start = time.monotonic()
        t_first_chunk = None
        audio_start = None
        chunk_count = 0

        streaming_parts: list[str] = []
        merged_stream_ref = [""]
        last_partial_ref = [""]
        full_audio_ref = [None]
        supports_streaming = getattr(self._asr, "supports_streaming", False)

        def on_speech_start():
            nonlocal audio_start
            audio_start = time.monotonic()
            log.debug("Speech detected ...")

        def on_chunk(chunk):
            nonlocal t_first_chunk, chunk_count
            # 检查取消
            if getattr(self, '_asr_cancel', None) and self._asr_cancel.is_set():
                return
            chunk_count += 1
            if self._asr:
                result = self._asr.feed_audio(chunk)
                if result and supports_streaming:
                    if t_first_chunk is None:
                        t_first_chunk = time.monotonic()
                    part = result.strip()
                    if part and part != last_partial_ref[0]:
                        last_partial_ref[0] = part
                        streaming_parts.append(part)
                        merged_stream_ref[0] = self._merge_streaming_pair(
                            merged_stream_ref[0], part
                        )
                        log.debug(f"[ASR] partial: '{merged_stream_ref[0]}'")

        def on_speech_end(full_audio):
            full_audio_ref[0] = full_audio

        self._asr.start_stream()

        log.debug(f"[ASR] stream started, supports_streaming={supports_streaming}")

        # Reset cancel event for this recording session
        if hasattr(self, '_asr_cancel'):
            self._asr_cancel.clear()

        self._audio_input.record_until_silence(
            on_speech_start=on_speech_start,
            on_chunk=on_chunk,
            on_speech_end=on_speech_end,
            cancel_event=getattr(self, '_asr_cancel', None),
        )

        full_audio = full_audio_ref[0]
        final = (self._asr.end_stream() or "").strip()
        merged_stream = merged_stream_ref[0] or self._merge_streaming_results(
            streaming_parts
        )

        if supports_streaming and not final:
            final = merged_stream
        elif (
            supports_streaming
            and merged_stream
            and len(merged_stream) > len(final) + 1
            and final in merged_stream
        ):
            final = merged_stream

        # 离线兜底：流式结果差时用完整音频重新识别
        if full_audio is not None and len(full_audio) > 0:
            duration_sec = len(full_audio) / max(1, self.config.audio.sample_rate)
            if not final or len(final) <= 2:
                if duration_sec >= 0.35:
                    try:
                        a = full_audio.flatten()
                        rms = float(np.sqrt(np.mean(a ** 2))) if a.size > 0 else 0
                        if rms >= 0.002:
                            offline = self._asr.recognize_audio(
                                full_audio, self.config.audio.sample_rate,
                            )
                            if offline and len(offline) > len(final or ""):
                                log.info(f"[ASR] 离线兜底: '{final}' -> '{offline.strip()}'")
                                final = offline.strip()
                    except Exception as e:
                        log.warn(f"离线识别失败: {e}")

        # Record ASR performance metrics
        t_end = time.monotonic()
        if final and audio_start:
            audio_duration_ms = (t_end - audio_start) * 1000
            total_latency_ms = (t_end - t_start) * 1000
            first_chunk_latency_ms = (
                (t_first_chunk - t_start) * 1000 if t_first_chunk else total_latency_ms
            )
            rtf = (
                total_latency_ms / audio_duration_ms
                if audio_duration_ms > 0
                else 0.0
            )
            metrics = ASRMetrics(
                first_chunk_latency_ms=first_chunk_latency_ms,
                total_latency_ms=total_latency_ms,
                rtf=rtf,
                audio_duration_ms=audio_duration_ms,
                text_length=len(final),
            )
            self._perf_monitor.record_asr(metrics)
            log.debug(
                f"[ASR perf] first-chunk: {first_chunk_latency_ms:.1f}ms, "
                f"total: {total_latency_ms:.1f}ms, RTF: {rtf:.3f}"
            )

        # Speaker identification (after ASR, before return)
        if final and full_audio is not None and self._diarization is not None:
            try:
                speaker_id = self._identify_speaker(full_audio)
                if speaker_id:
                    log.debug(f"[ASR] speaker identified: {speaker_id}")
            except Exception as e:
                log.debug(f"[ASR] speaker identification skipped: {e}")

        # Extract speaker embedding for passive registration
        if final and full_audio is not None and self._sv is not None:
            try:
                self._last_speaker_embedding = self._sv.embed(
                    full_audio, sample_rate=self.config.audio.sample_rate
                )
            except Exception as e:
                log.debug(f"[ASR] speaker embedding extraction failed: {e}")
                self._last_speaker_embedding = None

        if final:
            log.debug(f"[ASR] final: '{final}'")
        return final or None

    def _listen_with_text(self: "AsyncConversationManager") -> Optional[str]:
        """Fallback text input (debug mode)."""
        try:
            text = input("\nPlease type (or 'quit' to exit): ").strip()
            return text if text else None
        except EOFError:
            return None

    # -- Text submission ----------------------------------------------------

    def submit_user_text(self: "AsyncConversationManager", text: str):
        """Thread-safe: post user text into the conversation loop."""
        queue = self._user_text_queue
        if queue is None:
            return
        loop = getattr(self, '_loop', None)
        if loop and loop.is_running():
            loop.call_soon_threadsafe(queue.put_nowait, text)
        else:
            log.warning("[conversation] submit_user_text: no running loop, message dropped")

    # -- Streaming text helpers ---------------------------------------------

    @staticmethod
    def _merge_streaming_pair(base: str, incoming: str) -> str:
        """Merge two overlapping streaming-text fragments."""
        b = (base or "").strip()
        p = (incoming or "").strip()
        if not p:
            return b
        if not b:
            return p
        if p.startswith(b):
            return p
        if b.startswith(p):
            return b
        max_overlap = min(len(b), len(p))
        for i in range(max_overlap, 0, -1):
            if b.endswith(p[:i]):
                return b + p[i:]
        return b + p

    def _merge_streaming_results(self, parts: list) -> str:
        """Merge a list of streaming recognition fragments."""
        merged = ""
        for p in parts or []:
            merged = self._merge_streaming_pair(merged, p)
        return merged

    # -- Emotion tag stripping ----------------------------------------------

    @staticmethod
    def _strip_emotion_tags(text: str) -> tuple[str, str | None]:
        """Remove ``[emotion]`` tags; return ``(clean_text, first_emotion)``."""
        emotions_found = _EMOTION_PATTERN.findall(text)
        first_tag = emotions_found[0].lower() if emotions_found else None
        clean_text = _EMOTION_PATTERN.sub("", text).strip()
        clean_text = re.sub(r'  +', ' ', clean_text)
        return clean_text, first_tag
