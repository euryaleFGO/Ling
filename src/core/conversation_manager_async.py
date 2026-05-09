# -*- coding: utf-8 -*-
"""
Asynchronous conversation manager (Yione-inspired architecture).

Orchestrates ASR -> Agent -> TTS into a complete dialogue loop with streaming
interrupt support.  Heavy-lift modules have been extracted into:

* ``conversation_component_init``  -- ASR / TTS / Agent / audio init
* ``conversation_tts_pipeline``    -- TTS worker, viseme / RMS helpers
* ``conversation_message_handler`` -- LLM streaming, ASR listening, emotion tags

This file keeps the thin orchestrator: lifecycle, state, turn management, and
the main async loop.
"""

import asyncio
import contextlib
import logging
import time
import threading
from typing import Optional, Callable

import numpy as np

from core.log import log
from core.config_manager import SystemConfig, get_config_manager
from core.emotion_classifier import EmotionClassifier
from core.sv_engine import SVEngine
from core.performance_metrics import PerformanceMonitor, InterruptMetrics
from core.conversation import ConversationState, TurnMetrics
from core.conversation.sentence_splitter import pop_sentence as _pop_sentence
from core import exit_signal

# Mixins (imported for composition; also available for direct use)
from core.conversation_component_init import ComponentInitMixin
from core.conversation_tts_pipeline import (
    TTSPipelineMixin,
    TurnState,
    PendingSentence,
    PendingItem,
)
from core.conversation_message_handler import MessageHandlerMixin
from core.conversation_speaker import SpeakerRecognitionMixin

logger = logging.getLogger(__name__)


# ============================================================
#  AsyncConversationManager
# ============================================================

class AsyncConversationManager(
    ComponentInitMixin,
    TTSPipelineMixin,
    MessageHandlerMixin,
    SpeakerRecognitionMixin,
):
    """
    Asynchronous conversation manager (Yione-inspired architecture).

    Core design:
    1. asyncio.Task-based cancellable architecture
    2. TTS Worker + Pending Queue decoupling
    3. Smart sentence splitting (hard + soft)
    4. Deduplication and debounce
    """

    def __init__(self, config: SystemConfig = None):
        self.config = config or get_config_manager().config
        self.state = ConversationState.IDLE

        # Components (lazy init)
        self._asr = None
        self._tts = None
        self._tts_mode = None
        self._singing = None  # DiffSinger 歌声合成引擎
        self._agent = None
        self._audio_input = None
        self._audio_output = None

        # Callbacks
        self._on_state_change: Optional[Callable] = None
        self._on_user_text: Optional[Callable] = None
        self._on_ai_text: Optional[Callable] = None
        self._on_subtitle: Optional[Callable] = None
        self._on_audio_rms: Optional[Callable] = None
        self._on_viseme: Optional[Callable] = None
        self._on_exit_requested: Optional[Callable] = None

        # Emotion state
        self._current_emotion: str = "neutral"
        self._emotion_classifier = EmotionClassifier()

        # SER engine
        self._ser = None

        # PUNC engine
        self._punc = None

        # Speaker verification
        self._sv: SVEngine | None = None

        # Multi-speaker diarization
        self._diarization = None
        self._user_id: str = self.config.general.user_id
        self._current_user_id: str = self._user_id
        self._on_speaker_change_callback: Optional[Callable] = None
        self._speaker_manager = None
        self._voiceprint_db = None

        # Passive speaker registration state
        self._pending_registration = False
        self._last_unknown_embedding = None
        self._last_speaker_embedding = None

        # Turn management (Yione)
        self._current_turn: asyncio.Task | None = None

        # Interrupt stats
        self._interrupt_count: int = 0

        # Barge-in interrupt detection (P0-2)
        self._interrupt_detected = threading.Event()

        # ASR 可中断控制
        self._asr_cancel = threading.Event()

        # Deduplication (Yione)
        self._last_submitted: dict[str, float] = {}
        self._dedup_window_ms: int = 2000

        # Performance monitoring
        self._perf_monitor: PerformanceMonitor = PerformanceMonitor()
        self._current_turn_start: float = 0.0
        self._current_turn_id: str = ""

        # TTS cache
        self._tts_cache = None

        # Text-input queue (fed by tray / message_server)
        self._user_text_queue: asyncio.Queue | None = None

        # 热更新待执行标志（event loop 内调度，无线程竞争）
        self._reload_pending: dict[str, bool] = {}

        # Event loop reference (set in run_async, init to None for safe access)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Running flag (threading.Event for cross-thread safety)
        self._running = threading.Event()

    # ============================================================
    #  Callback management
    # ============================================================

    def set_callbacks(
        self,
        on_state_change: Callable[[ConversationState], None] = None,
        on_user_text: Callable[[str], None] = None,
        on_ai_text: Callable[[str], None] = None,
        on_subtitle: Callable[[str, bool, str], None] = None,
        on_audio_rms: Callable[[float], None] = None,
        on_viseme: Callable[[float, float], None] = None,
        on_exit_requested: Callable[[str], None] = None,
        on_speaker_change: Callable[[str, float], None] = None,
    ):
        """Register UI / external callbacks."""
        self._on_state_change = on_state_change
        self._on_user_text = on_user_text
        self._on_ai_text = on_ai_text
        self._on_subtitle = on_subtitle
        self._on_audio_rms = on_audio_rms
        self._on_viseme = on_viseme
        self._on_exit_requested = on_exit_requested
        self._on_speaker_change_callback = on_speaker_change

    @property
    def event_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """公共接口：获取 event loop 引用"""
        return getattr(self, '_loop', None)

    # ============================================================
    #  State management
    # ============================================================

    def _set_state(self, state: ConversationState):
        old_state = self.state
        self.state = state
        log.debug(f"[conversation] state: {old_state.value} -> {state.value}")
        if self._on_state_change:
            self._on_state_change(state)

    def _send_subtitle(self, text: str, is_final: bool = False, emotion: str = "neutral"):
        if self._on_subtitle:
            self._on_subtitle(text, is_final, emotion)

    # ============================================================
    #  Turn processing (orchestration)
    # ============================================================

    async def _handle_user_message(self, user_text: str) -> None:
        """Execute one full user turn.  Cancellation triggers graceful teardown."""
        t0 = time.monotonic()
        self._current_turn_start = t0
        self._current_turn_id = f"turn_{int(t0 * 1000)}"

        log.info(f"[0.00s] User message: {user_text[:40]}...")

        # 设置说话人上下文到 Agent
        if self._agent and hasattr(self._agent, 'set_speaker_context'):
            is_unknown = self._current_user_id.startswith("unknown_")
            self._agent.set_speaker_context(self._current_user_id, is_unknown)

        self._set_state(ConversationState.PROCESSING)

        pending: asyncio.Queue[PendingItem] = asyncio.Queue()
        state = TurnState(t0=t0)
        worker = asyncio.create_task(self._tts_worker(pending, state))

        # Two buffers: raw keeps LLM output (incl. tags), clean is subtitle text
        raw = ""
        clean = ""
        unspoken = ""
        first_chunk = True

        t_llm_first = None
        t_tts_first = None
        interrupted = False

        try:
            async for chunk in self._stream_agent_reply(user_text):
                if first_chunk:
                    t_llm_first = time.monotonic()
                    log.info(f"[{t_llm_first - t0:.2f}s] LLM first-chunk: {chunk[:20]}...")
                    first_chunk = False

                raw += chunk
                new_clean, last_tag = self._strip_emotion_tags(raw)
                if last_tag is not None:
                    state.current_emotion = last_tag

                delta = new_clean[len(clean):]
                clean = new_clean
                unspoken += delta

                self._send_subtitle(clean, is_final=False, emotion=state.current_emotion)

                # Sentence splitting
                while True:
                    sentence, unspoken = _pop_sentence(unspoken)
                    if sentence is None:
                        break

                    sentence_emotion = self._emotion_classifier.classify(sentence).emotion
                    if sentence_emotion != "neutral":
                        state.current_emotion = sentence_emotion

                    state.sentences_queued += 1

                    if t_tts_first is None and state.sentences_queued == 1:
                        t_tts_first = time.monotonic()

                    log.info(
                        f"[{time.monotonic() - t0:.2f}s] queued sentence #{state.sentences_queued} "
                        f"({state.current_emotion}): {sentence[:30]}..."
                    )
                    await pending.put(
                        PendingSentence(text=sentence, emotion=state.current_emotion)
                    )

            log.info(
                f"[{time.monotonic() - t0:.2f}s] LLM done, "
                f"clean={len(clean)} chars, unspoken={unspoken[:40]}..."
            )

            self._send_subtitle(clean, is_final=True, emotion=state.current_emotion)

            if unspoken.strip():
                state.sentences_queued += 1
                await pending.put(
                    PendingSentence(text=unspoken, emotion=state.current_emotion)
                )

            await pending.put(None)
            self._set_state(ConversationState.SPEAKING)

            # 启动打断检测（P0-2）
            if self.config.interrupt.enable_barge_in and self._audio_input:
                self._interrupt_detected.clear()
                self._audio_input.start_interrupt_detection(
                    on_interrupt=self._on_barge_in_detected,
                    config=self.config.interrupt,
                )

            await worker

            # 停止打断检测
            if self._audio_input:
                self._audio_input.stop_interrupt_detection()

            log.info(f"[{time.monotonic() - t0:.2f}s] All segments played")
            self._set_state(ConversationState.IDLE)

            # TTS 播完后，检查是否有待处理的退出请求（exit_app 工具暂存的）
            pending_reason = exit_signal.consume_pending_exit()
            if pending_reason is not None:
                log.info(f"[conversation] pending exit promoted after TTS: {pending_reason}")
                exit_signal.request_exit(pending_reason)

            # 短暂等待（麦克风已在 TTS worker 中恢复）
            await asyncio.sleep(0.1)

            t_end = time.monotonic()
            turn_metrics = TurnMetrics(
                turn_id=self._current_turn_id,
                user_text=user_text,
                ai_text=clean,
                llm_first_token_ms=(t_llm_first - t0) * 1000 if t_llm_first else 0.0,
                llm_total_ms=(t_end - t0) * 1000,
                tts_first_chunk_ms=(t_tts_first - t0) * 1000 if t_tts_first else 0.0,
                total_latency_ms=(t_end - t0) * 1000,
                interrupted=interrupted,
            )
            self._perf_monitor.record_turn(turn_metrics)

        except asyncio.CancelledError:
            interrupted = True
            # 立即停止音频播放
            try:
                import sounddevice as sd
                sd.stop()
            except Exception as e:
                log.debug(f"[conversation] sd.stop() failed: {e}")
            # 停止打断检测
            if self._audio_input:
                self._audio_input.stop_interrupt_detection()
            # 用户打断 -> 丢弃暂存的退出请求，对话继续
            exit_signal.consume_pending_exit()
            # 确保麦克风不会停留在暂停状态
            if self._audio_input:
                await asyncio.to_thread(self._audio_input.resume_after_tts)

            t_end = time.monotonic()
            log.info(f"[{t_end - t0:.2f}s] Turn interrupted")

            turn_metrics = TurnMetrics(
                turn_id=self._current_turn_id,
                user_text=user_text,
                ai_text=clean,
                llm_first_token_ms=(t_llm_first - t0) * 1000 if t_llm_first else 0.0,
                llm_total_ms=(t_end - t0) * 1000,
                tts_first_chunk_ms=(t_tts_first - t0) * 1000 if t_tts_first else 0.0,
                total_latency_ms=(t_end - t0) * 1000,
                interrupted=True,
            )
            self._perf_monitor.record_turn(turn_metrics)

            self._drain_queue(pending)
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
            with contextlib.suppress(Exception):
                self._set_state(ConversationState.IDLE)
            raise
        except Exception:
            logger.exception("Turn failed")
            # 停止打断检测
            if self._audio_input:
                self._audio_input.stop_interrupt_detection()
            # 立即停止音频播放
            try:
                import sounddevice as sd
                sd.stop()
            except Exception as e:
                log.debug(f"[conversation] sd.stop() failed: {e}")
            # 异常时也丢弃暂存退出，确保麦克风恢复
            exit_signal.consume_pending_exit()
            if self._audio_input:
                await asyncio.to_thread(self._audio_input.resume_after_tts)
            self._drain_queue(pending)
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
            with contextlib.suppress(Exception):
                self._set_state(ConversationState.IDLE)
            raise

    # ============================================================
    #  Turn management
    # ============================================================

    async def cancel_current_turn(self) -> None:
        """Cancel the current turn (triggered by user interrupt)."""
        t = self._current_turn
        if t is None or t.done():
            return

        t_interrupt_start = time.monotonic()

        log.info("[interrupt] Cancelling current turn")
        self._interrupt_count += 1

        t.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t
        self._current_turn = None

        t_interrupt_end = time.monotonic()
        response_time_ms = (t_interrupt_end - t_interrupt_start) * 1000

        interrupt_metrics = InterruptMetrics(
            response_time_ms=response_time_ms,
            detection_latency_ms=0.0,
            stop_latency_ms=response_time_ms,
            interrupted_at_ms=(
                (t_interrupt_start - self._current_turn_start) * 1000
                if self._current_turn_start
                else 0.0
            ),
            total_duration_ms=(
                (t_interrupt_end - self._current_turn_start) * 1000
                if self._current_turn_start
                else 0.0
            ),
        )
        self._perf_monitor.record_interrupt(interrupt_metrics)

        if self.config.interrupt.feedback_enabled:
            self._send_subtitle("[interrupted]", is_final=True, emotion="neutral")

        log.info(
            f"[interrupt stats] total interrupts: {self._interrupt_count}, "
            f"response time: {response_time_ms:.1f}ms"
        )

        # 重置声纹注册状态
        self._pending_registration = False
        self._last_unknown_embedding = None

    def run_turn(self, user_text: str) -> None:
        """Start a new turn as an asyncio task."""
        self._current_turn = asyncio.create_task(self._handle_user_message(user_text))

    def _on_barge_in_detected(self) -> None:
        """打断检测回调：设置标志并取消当前 turn。"""
        log.info("[barge-in] User speech detected during TTS, interrupting")
        self._interrupt_detected.set()
        if self._current_turn and not self._current_turn.done():
            # 在事件循环中取消当前 turn
            try:
                loop = getattr(self, '_loop', None) or self._current_turn.get_loop()
                loop.call_soon_threadsafe(self._current_turn.cancel)
            except Exception as e:
                log.debug(f"[barge-in] cancel failed: {e}")

    # ============================================================
    #  Deduplication
    # ============================================================

    def _should_submit(self, text: str) -> bool:
        """Return *True* if *text* should be processed (dedup check)."""
        now = time.time() * 1000
        last_time = self._last_submitted.get(text)

        if last_time and (now - last_time) < self._dedup_window_ms:
            log.debug(f"[dedup] Ignoring duplicate: {text[:30]}...")
            return False

        self._last_submitted[text] = now

        cutoff = now - self._dedup_window_ms * 2
        self._last_submitted = {
            k: v for k, v in self._last_submitted.items() if v > cutoff
        }
        return True

    # ============================================================
    #  Config hot-reload
    # ============================================================

    def _schedule_reload(self, section: str):
        """标记一个 section 需要 reload（线程安全，可从任意线程调用）"""
        self._reload_pending[section] = True

    async def _execute_pending_reloads(self):
        """在主循环中执行待处理的 reload（event loop 单线程，无竞争）"""
        if not self._reload_pending:
            return
        pending = dict(self._reload_pending)
        self._reload_pending.clear()

        reload_map = {
            "asr": "reload_asr",
            "tts": "reload_tts",
            "audio": "reload_audio",
            "singing": "reload_singing",
            "interrupt": "reload_interrupt",
            "general": "reload_general",
            "models": "reload_models",
        }
        for section, should_reload in pending.items():
            if not should_reload:
                continue
            method_name = reload_map.get(section.lower())
            if method_name and hasattr(self, method_name):
                log.info(f"[conversation] hot-reloading {section} ...")
                try:
                    await asyncio.to_thread(getattr(self, method_name))
                except Exception as e:
                    log.warning(f"[conversation] reload {section} failed: {e}")

    async def _hot_reload_components(self):
        """检查配置文件更新，标记需要 reload 的组件"""
        try:
            cfg = get_config_manager()
            if not cfg.reload_if_changed():
                return

            log.info("[conversation] Config changed, checking components ...")

            # Initialize _old_config on first call
            if not hasattr(self, '_old_config'):
                self._old_config = {}

            # Capture old values before updating (I-7: stale reference fix)
            old_asr_provider = self.config.asr.provider
            old_asr_remote_url = self.config.asr.remote_url
            old_asr_device = self.config.asr.device
            old_asr_stream_profile = self.config.asr.stream_profile
            old_tts_remote_url = self.config.tts.remote_url
            old_tts_spk_id = self.config.tts.spk_id

            # Update to new config
            self.config = cfg.config

            # ---- ASR config ----
            if (old_asr_provider != self.config.asr.provider or
                    old_asr_remote_url != self.config.asr.remote_url or
                    old_asr_device != self.config.asr.device or
                    old_asr_stream_profile != self.config.asr.stream_profile):
                log.info("[热更新] ASR 配置变更，标记 reload")
                self._schedule_reload("asr")

            # ---- TTS config ----
            if (old_tts_remote_url != self.config.tts.remote_url or
                    old_tts_spk_id != self.config.tts.spk_id):
                log.info("[热更新] TTS 配置变更，标记 reload")
                self._schedule_reload("tts")

            # ---- Audio config ----
            old_audio = self._old_config.get("audio", {})
            new_audio = {
                "sample_rate": self.config.audio.sample_rate,
                "silence_threshold": self.config.audio.silence_threshold,
                "silence_duration": self.config.audio.silence_duration,
                "vad_backend": self.config.audio.vad_backend,
                "use_vad": self.config.audio.use_vad,
            }
            if old_audio != new_audio:
                log.info("[热更新] audio 配置变更，标记 reload")
                self._schedule_reload("audio")
                self._old_config["audio"] = new_audio

            # ---- Interrupt config ----
            old_int = self._old_config.get("interrupt", {})
            new_int = {
                "enable_barge_in": self.config.interrupt.enable_barge_in,
                "min_speech_ms": self.config.interrupt.min_speech_ms,
                "vad_threshold": self.config.interrupt.vad_threshold,
            }
            if old_int != new_int:
                log.info("[热更新] interrupt 配置变更，标记 reload")
                self._schedule_reload("interrupt")
                self._old_config["interrupt"] = new_int

            # ---- Singing config ----
            old_singing = self._old_config.get("singing", {})
            new_singing = {
                "enable": getattr(self.config.singing, 'enable', False),
                "device": getattr(self.config.singing, 'device', 'cuda'),
                "diffsinger_root": getattr(self.config.singing, 'diffsinger_root', ''),
            }
            if old_singing != new_singing:
                log.info("[热更新] singing 配置变更，标记 reload")
                self._schedule_reload("singing")
                self._old_config["singing"] = new_singing

            # ---- General config ----
            old_general = self._old_config.get("general", {})
            new_general = {
                "use_text_input": getattr(self.config.general, 'use_text_input', False),
                "auto_listen": getattr(self.config.general, 'auto_listen', True),
                "ws_api_key": getattr(self.config.general, 'ws_api_key', ''),
            }
            if old_general != new_general:
                log.info("[热更新] general 配置变更，标记 reload")
                self._schedule_reload("general")
                self._old_config["general"] = new_general

            # ---- Model services config (punc, ser, sv, diarization) ----
            old_models = self._old_config.get("models", {})
            new_models = {
                "punc_enable": getattr(self.config.punc, 'enable', True),
                "ser_enable": getattr(self.config.ser, 'enable', True),
                "sv_enable": getattr(self.config.sv, 'enable', False),
                "diar_enable": getattr(self.config.diarization, 'enable', False),
                "diar_threshold": getattr(self.config.diarization, 'threshold', 0.75),
            }
            if old_models != new_models:
                log.info("[热更新] 模型服务配置变更，标记 reload")
                self._schedule_reload("models")
                self._old_config["models"] = new_models

        except Exception as e:
            log.warning(f"[conversation] Config hot-reload check failed: {e}")

    # ============================================================
    #  Main loop
    # ============================================================

    async def run_async(self):
        """Async main conversation loop."""
        log.info("\nAsync conversation system started\n")
        self._running.set()
        self._loop = asyncio.get_running_loop()

        # 启动会话轮转调度器（每天凌晨 4 点新开会话）
        self._start_session_scheduler()

        # 启动梦境整合调度器（每天凌晨 4:30 执行记忆整合）
        self._start_dream_scheduler()

        # 将事件循环引用传递给调度器，使其可以安全地调度 async 操作
        if hasattr(self, '_session_scheduler') and self._session_scheduler:
            self._session_scheduler.set_loop(self._loop)

        if self.config.general.use_text_input:
            self._user_text_queue = asyncio.Queue()
            log.info("[text-input] Queue created, waiting for submissions ...")

        try:
            while self._running.is_set():
                # 检查配置文件更新
                try:
                    await self._hot_reload_components()
                except Exception as e:
                    log.warning(f"[conversation] Config hot-reload failed: {e}")

                # 执行待处理的 reload
                try:
                    await self._execute_pending_reloads()
                except Exception as e:
                    log.warning(f"[conversation] Pending reload failed: {e}")

                # 检查 exit_app 工具是否请求了退出
                if exit_signal.is_exit_requested():
                    reason = exit_signal.consume_exit_request()
                    log.info(f"[conversation] exit_app requested: {reason}")
                    break

                try:
                    self._set_state(ConversationState.LISTENING)
                    user_text = await self._listen_and_recognize_async()

                    if not user_text:
                        continue

                    if user_text.lower() in ['quit', 'exit', '退出', '结束']:
                        log.debug("Exit command received")
                        break

                    # Passive speaker registration (only when we have a real embedding)
                    if self._last_speaker_embedding is not None:
                        speaker_id = self._identify_speaker_from_embedding(
                            self._last_speaker_embedding
                        )
                        effective_text, should_continue, prompt_to_speak = (
                            self._handle_passive_registration(
                                user_text, speaker_id,
                                self._last_speaker_embedding,
                            )
                        )
                        if prompt_to_speak:
                            await asyncio.to_thread(self._speak_text_sync, prompt_to_speak)
                            self._send_subtitle(prompt_to_speak, is_final=True)
                        if not should_continue:
                            continue
                        if effective_text:
                            user_text = effective_text

                    if not self._should_submit(user_text):
                        continue

                    logger.info(f"\nUser: {user_text}")
                    if self._on_user_text:
                        self._on_user_text(user_text)

                    await self.cancel_current_turn()
                    self.run_turn(user_text)

                    if self._current_turn:
                        try:
                            await self._current_turn
                        except asyncio.CancelledError:
                            pass

                except KeyboardInterrupt:
                    logger.info("\nUser interrupted")
                    break
                except Exception as e:
                    log.error(f"Conversation error: {e}")
                    import traceback
                    traceback.print_exc()
                    await asyncio.sleep(1)
        finally:
            self._running.clear()
            # 中断 ASR
            if hasattr(self, '_asr_cancel'):
                self._asr_cancel.set()
            # 取消当前轮次
            if hasattr(self, '_current_turn') and self._current_turn and not self._current_turn.done():
                self._current_turn.cancel()
            # 停止调度器
            if hasattr(self, '_session_scheduler') and self._session_scheduler:
                try:
                    self._session_scheduler.stop()
                except Exception as e:
                    log.debug(f"[conversation] session_scheduler stop failed: {e}")
            if hasattr(self, '_dream_scheduler') and self._dream_scheduler:
                try:
                    self._dream_scheduler.stop()
                except Exception as e:
                    log.debug(f"[conversation] dream_scheduler stop failed: {e}")
            # 清理音频输入
            if self._audio_input and hasattr(self._audio_input, 'stop_listening'):
                try:
                    self._audio_input.stop_listening()
                except Exception as e:
                    log.debug(f"[conversation] audio_input.stop_listening() failed: {e}")
            # 退出时关闭会话，生成摘要
            if self._agent:
                try:
                    self._agent.end_chat(auto_summarize=True)
                except Exception as e:
                    log.error(f"[conversation] 退出时关闭会话失败: {e}")

            # 清理 TTS/ASR/音频资源
            for attr in ('_tts', '_asr', '_singing'):
                obj = getattr(self, attr, None)
                if obj and hasattr(obj, 'stop'):
                    try:
                        obj.stop()
                    except Exception as e:
                        log.debug(f"[conversation] {attr}.stop() failed: {e}")
            if hasattr(self, '_audio_output') and self._audio_output:
                try:
                    self._audio_output.stop()
                except Exception as e:
                    log.debug(f"[conversation] audio_output stop failed: {e}")

        log.info("Async conversation loop exited")

    # ============================================================
    #  Simple TTS speak (for prompts, registration, etc.)
    # ============================================================

    def _speak_text_sync(self, text: str):
        """Synchronously speak a short text via TTS (blocking)."""
        if not self._tts or not self._audio_output:
            return
        try:
            sr = getattr(self._tts, 'sample_rate', self.config.audio.sample_rate)
            for chunk_data in self._tts.generate_audio_streaming(text, use_clone=True):
                if chunk_data is None:
                    break
                audio = getattr(chunk_data, 'audio', chunk_data)
                if audio is not None:
                    self._audio_output.play_array(audio, sr, blocking=True)
        except Exception as e:
            log.warning(f"[tts] speak prompt failed: {e}")

    # ============================================================
    #  Performance monitoring
    # ============================================================

    def get_performance_stats(self) -> dict:
        return self._perf_monitor.get_summary()

    def print_performance_stats(self):
        self._perf_monitor.print_summary()

    def reset_performance_stats(self):
        self._perf_monitor.reset()

    # ============================================================
    #  Lifecycle
    # ============================================================

    def start(self, blocking: bool = True):
        """Start the conversation loop."""
        self.initialize()

        if blocking:
            asyncio.run(self.run_async())
        else:
            import threading as _threading
            def run_in_thread():
                asyncio.run(self.run_async())
            thread = _threading.Thread(target=run_in_thread, daemon=True)
            thread.start()

    def _start_session_scheduler(self):
        """启动会话轮转调度器"""
        try:
            from backend.llm.memory.session_scheduler import start_session_scheduler
            schedule_time = getattr(self.config.general, 'session_rotate_time', '04:00')
            self._session_scheduler = start_session_scheduler(
                agent=self._agent,
                context_manager=self._agent._context_manager if self._agent else None,
                schedule_time=schedule_time,
                enabled=True
            )
        except Exception as e:
            log.error(f"[conversation] 启动会话调度器失败: {e}")

    def _start_dream_scheduler(self):
        """启动梦境整合调度器"""
        try:
            from backend.llm.memory.dream_scheduler import start_dream_scheduler
            user_id = self._user_id
            self._dream_scheduler = start_dream_scheduler(
                user_id=user_id,
                schedule_time="04:30",
                days_back=7,
                enabled=True
            )
        except Exception as e:
            log.error(f"[conversation] 启动梦境调度器失败: {e}")

    async def stop(self):
        """Stop the conversation (async)."""
        log.info("[conversation] Stopping async conversation system ...")
        await self.cancel_current_turn()
        if self._audio_output:
            self._audio_output.stop()
        if self._audio_input:
            self._audio_input.stop_listening()
        if self._asr and hasattr(self._asr, 'stop'):
            self._asr.stop()
        log.info("[conversation] Async conversation system stopped")

    def stop_sync(self):
        """Stop the conversation (sync, safe from non-async contexts)."""
        self._running.clear()
        self._user_text_queue = None

        # 中断 ASR 录音
        if hasattr(self, '_asr_cancel'):
            self._asr_cancel.set()

        # 停止调度器
        if hasattr(self, '_session_scheduler') and self._session_scheduler:
            self._session_scheduler.stop()
        if hasattr(self, '_dream_scheduler') and self._dream_scheduler:
            self._dream_scheduler.stop()

        # 清理歌声合成引擎
        if self._singing and hasattr(self._singing, 'cleanup'):
            self._singing.cleanup()

        if self._audio_output:
            self._audio_output.stop()
        if self._audio_input:
            self._audio_input.stop_listening()
        if self._asr and hasattr(self._asr, 'stop'):
            self._asr.stop()
        log.info("[conversation] Async conversation system stopped (sync call)")


# ============================================================
#  Convenience launcher
# ============================================================

def start_async_conversation(
    user_id: str = "default_user",
    blocking: bool = True,
) -> AsyncConversationManager:
    """Quick-start helper for async conversation."""
    cfg = get_config_manager().config
    manager = AsyncConversationManager(cfg)
    manager._user_id = user_id
    manager.start(blocking=blocking)
    return manager


if __name__ == "__main__":
    logger.info("Starting async conversation manager ...")
    start_async_conversation()
