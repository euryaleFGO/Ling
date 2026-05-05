# -*- coding: utf-8 -*-
"""
对话管理器
整合 ASR + Agent + TTS 实现完整对话流程

使用方式:
    from core.conversation_manager import ConversationManager

    manager = ConversationManager()
    manager.start()  # 开始对话循环

重构说明:
    原始文件 1561 行，已拆分为：
    - core.conversation.state:          数据类 (ConversationState/Config/TurnMetrics)
    - core.conversation.asr_handler:    ASR 相关 (ASRHandler mixin)
    - core.conversation.tts_handler:    TTS 相关 (TTSHandler mixin)
    - core.conversation.audio_handler:  音频 I/O (AudioHandler mixin)
    - core.conversation_manager:        编排层 (本文件)
"""

import logging
import time
import threading
import queue
from typing import Optional, Callable

logger = logging.getLogger(__name__)

from core.log import log
from core.exit_signal import consume_exit_request
from core.emotion_classifier import EmotionClassifier

# 从拆分后的模块导入
from core.conversation.state import ConversationState, ConversationConfig
from core.conversation.asr_handler import ASRHandler
from core.conversation.tts_handler import TTSHandler
from core.conversation.audio_handler import AudioHandler

# 向后兼容：允许 from core.conversation_manager import ConversationConfig 等
__all__ = [
    "ConversationManager",
    "ConversationState",
    "ConversationConfig",
    "start_conversation",
]


class ConversationManager(ASRHandler, TTSHandler, AudioHandler):
    """
    对话管理器

    核心功能:
    1. 监听用户语音 -> ASR 识别
    2. 用户文本 -> Agent 生成回复
    3. 回复文本 -> TTS 合成播放
    4. 循环等待下一轮对话
    """

    def __init__(self, config: ConversationConfig = None):
        self.config = config or ConversationConfig()
        self.state = ConversationState.IDLE

        # 组件（延迟初始化）
        self._asr = None
        self._tts = None
        self._tts_mode = None  # "local" 或 "remote"
        self._agent = None
        self._audio_input = None
        self._audio_output = None

        # 线程控制
        self._running = False
        self._conversation_thread = None
        self._message_queue = queue.Queue()

        # 回调
        self._on_state_change: Optional[Callable] = None
        self._on_user_text: Optional[Callable] = None
        self._on_ai_text: Optional[Callable] = None
        self._on_subtitle: Optional[Callable] = None
        self._on_audio_rms: Optional[Callable] = None
        self._on_viseme: Optional[Callable] = None
        self._on_exit_requested: Optional[Callable] = None

        # 情绪状态
        self._current_emotion: str = "neutral"
        self._emotion_classifier = EmotionClassifier()
        self._current_user_emotion: str = "neutral"
        self._ser = None
        self._punc = None
        self._sv = None

        # 多说话人识别（延迟初始化）
        self._diarization = None
        self._current_user_id: str = self.config.user_id
        self._on_speaker_change_callback: Optional[Callable] = None

        # 流式打断状态
        self._interrupt_monitoring = False
        self._interrupt_thread: Optional[threading.Thread] = None
        self._interrupt_vad = None
        self._interrupt_audio_input = None
        self._interrupted_text: str = ""
        self._interrupt_count: int = 0

        # 字幕服务
        self._subtitle_callback = None

        # 提醒管理器
        self._reminder_manager = None

    # ------------------------------------------------------------------
    # 组件初始化
    # ------------------------------------------------------------------

    def _init_agent(self):
        """初始化 Agent"""
        if self._agent is not None:
            return

        try:
            from backend.llm.agent import Agent

            self._agent = Agent(user_id=self.config.user_id)
            self._agent.start_chat()
            log.debug("[对话] Agent 初始化完成")
        except Exception as e:
            log.error(f"Agent 初始化失败: {e}")
            raise

    def _init_reminder(self):
        """初始化提醒管理器"""
        try:
            from backend.llm.tools.reminder_tool import ReminderManager

            self._reminder_manager = ReminderManager.get_instance()
            self._reminder_manager.initialize()
            self._reminder_manager.set_on_remind(self._on_reminder_triggered)
            self._reminder_manager.start()
            log.debug("[对话] 提醒管理器初始化完成")
        except Exception as e:
            log.warn(f"提醒管理器初始化失败（非致命）: {e}")
            self._reminder_manager = None

    def _on_reminder_triggered(self, reminder: dict):
        """提醒到期时的回调"""
        content = reminder.get("content", "提醒时间到了")
        notify_text = f"提醒：{content}"

        log.info(f"[提醒] 触发: {content}")
        log.info(f"\n{notify_text}")

        self._send_subtitle(notify_text, is_final=True, emotion="happy")

        if self._on_ai_text:
            self._on_ai_text(notify_text)

        if self._tts and self._audio_output:
            try:
                self._speak(f"提醒时间到了，{content}")
            except Exception as e:
                log.warn(f"提醒 TTS 播报失败: {e}")

    def initialize(self):
        """初始化所有组件"""
        log.debug("[对话] 正在初始化对话系统...")
        self._init_audio()
        self._init_tts()
        self._init_agent()
        self._init_reminder()
        self._init_ser()
        self._init_punc()
        self._init_sv()
        self._init_diarization()
        log.info("对话系统初始化完成")

    # ------------------------------------------------------------------
    # 回调 & 状态管理
    # ------------------------------------------------------------------

    def set_callbacks(
        self,
        on_state_change: Callable[[ConversationState], None] = None,
        on_user_text: Callable[[str], None] = None,
        on_ai_text: Callable[[str], None] = None,
        on_subtitle: Callable[[str, bool], None] = None,
        on_audio_rms: Callable[[float], None] = None,
        on_viseme: Callable[[float, float], None] = None,
        on_exit_requested: Callable[[str], None] = None,
    ):
        """设置回调函数"""
        self._on_state_change = on_state_change
        self._on_user_text = on_user_text
        self._on_ai_text = on_ai_text
        self._on_subtitle = on_subtitle
        self._on_audio_rms = on_audio_rms
        self._on_viseme = on_viseme
        self._on_exit_requested = on_exit_requested

    def _set_state(self, state: ConversationState):
        """设置状态"""
        old_state = self.state
        self.state = state
        log.debug(f"[对话] 状态: {old_state.value} -> {state.value}")
        if self._on_state_change:
            self._on_state_change(state)

    def _send_subtitle(
        self, text: str, is_final: bool = False, emotion: str = "neutral",
    ):
        """发送字幕（带情绪标签）"""
        if self._on_subtitle:
            self._on_subtitle(text, is_final, emotion)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self, blocking: bool = True):
        """启动对话循环"""
        if self._running:
            return

        self.initialize()
        self._running = True

        if blocking:
            self._conversation_loop()
        else:
            self._conversation_thread = threading.Thread(
                target=self._conversation_loop,
                daemon=True,
            )
            self._conversation_thread.start()

    def stop(self):
        """停止对话"""
        self._running = False

        if self._audio_input:
            self._audio_input.stop_listening()
        if self._audio_output:
            self._audio_output.stop()

        if self._reminder_manager:
            self._reminder_manager.stop()

        if self._agent:
            self._agent.end_chat()

        log.debug("对话已停止")

    # ------------------------------------------------------------------
    # 对话主循环
    # ------------------------------------------------------------------

    def _conversation_loop(self):
        """对话主循环"""
        log.info("\n对话系统已启动，说话开始对话，或输入 'quit' 退出\n")

        while self._running:
            try:
                # 1. 等待并获取用户输入
                self._set_state(ConversationState.LISTENING)
                t0_input = time.perf_counter()
                user_text = self._listen_and_recognize()
                elapsed_input = time.perf_counter() - t0_input
                if user_text:
                    log.debug(f"[耗时] 输入/ASR: {elapsed_input:.2f}s")
                if not user_text:
                    continue

                if user_text.lower() in ['quit', 'exit', '退出', '结束']:
                    log.debug("收到退出指令")
                    break

                log.info(f"\n用户: {user_text}")
                if self._on_user_text:
                    self._on_user_text(user_text)

                # 2. Agent 生成回复
                self._set_state(ConversationState.PROCESSING)
                t0_agent = time.perf_counter()
                ai_response = self._generate_response(user_text)
                elapsed_agent = time.perf_counter() - t0_agent
                log.debug(f"[耗时] Agent: {elapsed_agent:.2f}s")

                if not ai_response:
                    continue

                log.info(f"AI: {ai_response}")
                if self._on_ai_text:
                    self._on_ai_text(ai_response)

                # 3. TTS 播放
                self._set_state(ConversationState.SPEAKING)
                t0_tts = time.perf_counter()
                try:
                    if self._audio_input:
                        self._audio_input.stop_listening()
                except Exception:
                    logger.debug("Failed to stop audio input before TTS playback")
                    pass
                self._speak(ai_response)
                try:
                    if self._audio_input and self.config.auto_listen:
                        self._audio_input.start_listening()
                except Exception:
                    logger.debug("Failed to restart audio input after TTS playback")
                    pass
                log.debug(
                    f"[耗时] TTS+播放 总: {time.perf_counter() - t0_tts:.2f}s"
                )

                # Agent 工具请求退出
                exit_reason = consume_exit_request()
                if exit_reason is not None:
                    log.info(f"收到退出请求，准备退出程序: {exit_reason}")
                    if self._on_exit_requested:
                        try:
                            self._on_exit_requested(exit_reason)
                        except Exception as e:
                            log.warn(f"退出回调执行失败: {e}")
                    break

                # 4. 回到监听状态
                self._set_state(ConversationState.IDLE)

            except KeyboardInterrupt:
                log.info("\n用户中断")
                break
            except Exception as e:
                log.error(f"对话错误: {e}")
                import traceback
                log.error(traceback.format_exc())
                time.sleep(1)

        self.stop()

    # ------------------------------------------------------------------
    # Agent 响应生成
    # ------------------------------------------------------------------

    def _generate_response(self, user_text: str) -> Optional[str]:
        """生成 AI 回复（带情绪解析）"""
        if not self._agent:
            return "抱歉，AI 服务未初始化"

        try:
            user_input = user_text
            ue = (self._current_user_emotion or "neutral").strip().lower()
            if ue and ue != "neutral":
                user_input = (
                    f"（用户当前情绪：{self._emotion9_to_cn(ue)}）{user_text}"
                )

            response_parts = []
            last_sent_len = 0
            SUBTITLE_CHUNK = 6

            for chunk in self._agent.chat(user_input, stream=True):
                response_parts.append(chunk)
                current = "".join(response_parts)
                if len(current) - last_sent_len >= SUBTITLE_CHUNK:
                    clean, _ = self._parse_emotion(current)
                    self._send_subtitle(clean, is_final=False)
                    last_sent_len = len(current)

            full_response = "".join(response_parts)

            clean_text, emotion = self._parse_emotion(full_response)
            self._current_emotion = emotion

            self._send_subtitle(
                clean_text, is_final=False, emotion=emotion,
            )

            return clean_text

        except Exception as e:
            log.error(f"Agent 错误: {e}")
            return f"抱歉，处理时出错了: {e}"

    # ------------------------------------------------------------------
    # 手动触发方法（供外部调用）
    # ------------------------------------------------------------------

    def send_text(self, text: str):
        """手动发送文本（跳过 ASR），用于 GUI 文本输入或测试"""
        self._message_queue.put(("text", text))

    def trigger_listen(self):
        """手动触发监听"""
        self._message_queue.put(("listen", None))

    def interrupt(self):
        """打断当前操作"""
        if self.state == ConversationState.SPEAKING:
            self._audio_output.stop()
        self._set_state(ConversationState.IDLE)


# === 便捷启动函数 ===

def start_conversation(
    user_id: str = "default_user",
    blocking: bool = True,
) -> ConversationManager:
    """快速启动对话"""
    config = ConversationConfig(user_id=user_id)
    manager = ConversationManager(config)
    manager.start(blocking=blocking)
    return manager


if __name__ == "__main__":
    log.info("启动对话管理器...")
    start_conversation()
