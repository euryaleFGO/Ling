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

logger = logging.getLogger(__name__)


# ============================================================
#  AsyncConversationManager
# ============================================================

class AsyncConversationManager(
    ComponentInitMixin,
    TTSPipelineMixin,
    MessageHandlerMixin,
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
        self._current_user_id: str = self.config.general.user_id
        self._on_speaker_change_callback: Optional[Callable] = None
        self._speaker_manager = None
        self._voiceprint_db = None

        # Turn management (Yione)
        self._current_turn: asyncio.Task | None = None

        # Interrupt stats
        self._interrupt_count: int = 0

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
            await worker

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
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker
            with contextlib.suppress(Exception):
                self._set_state(ConversationState.IDLE)
            raise
        except Exception:
            logger.exception("Turn failed")
            # 异常时也丢弃暂存退出，确保麦克风恢复
            exit_signal.consume_pending_exit()
            if self._audio_input:
                await asyncio.to_thread(self._audio_input.resume_after_tts)
            self._drain_queue(pending)
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
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

    def run_turn(self, user_text: str) -> None:
        """Start a new turn as an asyncio task."""
        self._current_turn = asyncio.create_task(self._handle_user_message(user_text))

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
    #  Main loop
    # ============================================================

    async def run_async(self):
        """Async main conversation loop."""
        log.info("\nAsync conversation system started\n")
        self._running.set()

        if self.config.general.use_text_input:
            self._user_text_queue = asyncio.Queue()
            log.info("[text-input] Queue created, waiting for submissions ...")

        try:
            while self._running.is_set():
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
            # 退出时关闭会话，生成摘要
            if self._agent:
                try:
                    self._agent.end_chat(auto_summarize=True)
                except Exception as e:
                    log.error(f"[conversation] 退出时关闭会话失败: {e}")

        log.info("Async conversation loop exited")

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

        # 启动会话轮转调度器（每天凌晨 4 点新开会话）
        self._start_session_scheduler()

        # 启动梦境整合调度器（每天凌晨 4:30 执行记忆整合）
        self._start_dream_scheduler()

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
            user_id = self.config.general.user_id
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

        # 停止调度器
        if hasattr(self, '_session_scheduler') and self._session_scheduler:
            self._session_scheduler.stop()
        if hasattr(self, '_dream_scheduler') and self._dream_scheduler:
            self._dream_scheduler.stop()

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
    cfg.general.user_id = user_id
    manager = AsyncConversationManager(cfg)
    manager.start(blocking=blocking)
    return manager


if __name__ == "__main__":
    logger.info("Starting async conversation manager ...")
    start_async_conversation()
