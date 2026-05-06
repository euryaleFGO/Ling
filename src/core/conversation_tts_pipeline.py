# -*- coding: utf-8 -*-
"""
TTS streaming pipeline for AsyncConversationManager.

Provides the TTS worker coroutine, audio visualisation helpers (viseme / RMS),
and the pending-queue drain utility.  Designed to be mixed into
``AsyncConversationManager`` via multiple inheritance.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from core.log import log
from core.performance_metrics import TTSMetrics

if TYPE_CHECKING:
    from core.conversation_manager_async import AsyncConversationManager

logger = logging.getLogger(__name__)


# ============================================================
#  Turn-level shared state / payload dataclasses
# ============================================================

@dataclass
class TurnState:
    """LLM loop + TTS worker shared turn-level state."""
    t0: float
    next_idx: int = 0
    last_motion_emotion: str | None = None
    current_emotion: str = "neutral"
    sentences_queued: int = 0


@dataclass
class PendingSentence:
    """A single sentence with its pre-evaluated emotion for the TTS worker."""
    text: str
    emotion: str


# Sentinel: None in the queue means "no more sentences -- worker can finish".
PendingItem = PendingSentence | None


# ============================================================
#  Rhubarb viseme shape map
# ============================================================

VISEME_SHAPE_MAP: dict[str, tuple[float, float]] = {
    'X': (0.00, 0.00),   # closed mouth
    'A': (0.05, 0.00),   # very small opening
    'B': (0.25, 0.60),   # lips lightly pressed
    'C': (0.50, 0.20),   # medium opening
    'D': (0.85, 0.40),   # wide open
    'E': (0.55, -0.40),  # rounded lips
    'F': (0.35, -0.70),  # narrow lips
    'G': (0.20, 0.30),   # slight opening
    'H': (0.40, 0.10),   # medium opening
}


# ============================================================
#  Mixin
# ============================================================

class TTSPipelineMixin:
    """TTS worker, audio visualisation, and queue helpers.

    All methods reference ``self`` attributes that must exist on the final
    ``AsyncConversationManager`` instance (``_tts``, ``_audio_output``,
    ``_on_viseme``, ``_on_audio_rms``, ``_perf_monitor``).
    """

    # -- TTS worker --------------------------------------------------------

    async def _tts_worker(
        self: "AsyncConversationManager",
        pending: asyncio.Queue[PendingItem],
        state: TurnState,
    ) -> None:
        """Consume *pending*; for each sentence call TTS and play audio.

        ``None`` is the end sentinel.  Cancelling the task propagates
        ``CancelledError`` naturally.

        麦克风在 TTS 播报期间保持开启，用于用户打断（barge-in）检测。
        TTS 回声由 listen 循环开始时的 buffer flush 清除。
        """
        while True:
            item = await pending.get()
            if item is None:
                return

            try:
                t_tts_start = time.monotonic()
                t_first_chunk = None
                total_audio_duration = 0.0
                chunk_count = 0

                first = True

                def _sync_tts_gen():
                    for chunk_data in self._tts.generate_audio_streaming(
                        item.text, use_clone=True, max_workers=2
                    ):
                        yield chunk_data

                for chunk_data in await asyncio.to_thread(list, _sync_tts_gen()):
                    if len(chunk_data) == 4:
                        audio, seg_idx, total, visemes = chunk_data
                    else:
                        audio, seg_idx, total = chunk_data[:3]
                        visemes = None

                    state.next_idx += 1
                    chunk_count += 1

                    if first:
                        t_first_chunk = time.monotonic()
                        t_first = t_first_chunk - state.t0
                        log.info(
                            f"[{t_first:.2f}s] TTS first-chunk: "
                            f"{item.text[:20]}... -> idx={state.next_idx}"
                        )
                        first = False

                    audio_duration = len(audio) / max(1, self._tts.sample_rate)
                    total_audio_duration += audio_duration

                    # 播放音频与 viseme 并行，避免嘴型延迟
                    audio_task = asyncio.create_task(
                        asyncio.to_thread(
                            self._audio_output.play_array,
                            audio,
                            self._tts.sample_rate,
                            blocking=True,
                        )
                    )

                    if visemes and self._on_viseme:
                        viseme_task = asyncio.create_task(
                            self._send_visemes_async(visemes, audio, self._tts.sample_rate)
                        )
                        await asyncio.gather(audio_task, viseme_task)
                    elif self._on_audio_rms:
                        rms_task = asyncio.create_task(
                            self._send_rms_async(audio, self._tts.sample_rate)
                        )
                        await asyncio.gather(audio_task, rms_task)
                    else:
                        await audio_task

                # Record TTS performance metrics
                t_tts_end = time.monotonic()
                if t_first_chunk:
                    first_chunk_latency_ms = (t_first_chunk - t_tts_start) * 1000
                    total_latency_ms = (t_tts_end - t_tts_start) * 1000
                    audio_duration_ms = total_audio_duration * 1000
                    rtf = (
                        total_latency_ms / audio_duration_ms
                        if audio_duration_ms > 0
                        else 0.0
                    )
                    metrics = TTSMetrics(
                        first_chunk_latency_ms=first_chunk_latency_ms,
                        total_latency_ms=total_latency_ms,
                        rtf=rtf,
                        audio_duration_ms=audio_duration_ms,
                        text_length=len(item.text),
                        chunk_count=chunk_count,
                    )
                    self._perf_monitor.record_tts(metrics)
                    log.debug(
                        f"[TTS perf] first-chunk: {first_chunk_latency_ms:.1f}ms, "
                        f"total: {total_latency_ms:.1f}ms, RTF: {rtf:.3f}"
                    )

            except asyncio.CancelledError:
                # 打断：TTS 被取消，停止播放
                log.info("[TTS] cancelled (user interrupt)")
                raise
            except Exception as exc:
                log.error(f"TTS playback failed: {exc}")

    # -- Audio visualisation ------------------------------------------------

    async def _send_visemes_async(self, visemes, audio, sample_rate):
        """Asynchronously stream viseme (lip-shape) data to the UI callback."""
        try:
            if not visemes:
                return
            audio_duration = len(audio) / max(1, sample_rate)
            t0 = time.monotonic()
            interval = 1.0 / 30  # 30 fps

            cue_idx = 0
            current_shape = 'X'
            elapsed = 0.0

            while elapsed < audio_duration:
                while cue_idx < len(visemes) - 1:
                    next_start = visemes[cue_idx + 1].get('start', 999)
                    if elapsed >= next_start:
                        cue_idx += 1
                    else:
                        break

                current_shape = visemes[cue_idx].get('value', 'X')
                openY, form = VISEME_SHAPE_MAP.get(current_shape, (0.0, 0.0))

                if self._on_viseme:
                    await asyncio.to_thread(self._on_viseme, openY, form)

                await asyncio.sleep(interval)
                elapsed = time.monotonic() - t0

            if self._on_viseme:
                await asyncio.to_thread(self._on_viseme, 0.0, 0.0)
        except Exception as e:
            log.debug(f"Viseme send error: {e}")

    async def _send_rms_async(self, audio, sample_rate):
        """Asynchronously stream RMS energy data to the UI callback."""
        try:
            window_ms = 50
            window_samples = max(1, int(sample_rate * window_ms / 1000))

            audio_float = audio.astype(np.float32)
            max_val = np.max(np.abs(audio_float))
            if max_val > 1.0:
                audio_float = audio_float / 32768.0

            for i in range(0, len(audio_float), window_samples):
                window = audio_float[i : i + window_samples]
                rms = float(np.sqrt(np.mean(window ** 2)))
                if self._on_audio_rms:
                    await asyncio.to_thread(self._on_audio_rms, rms)
                await asyncio.sleep(window_ms / 1000.0)
        except Exception as e:
            log.debug(f"RMS send error: {e}")

    # -- Queue helpers ------------------------------------------------------

    @staticmethod
    def _drain_queue(q: asyncio.Queue[PendingItem]) -> None:
        """Discard all unprocessed items from *q*."""
        try:
            while True:
                q.get_nowait()
        except asyncio.QueueEmpty:
            return
