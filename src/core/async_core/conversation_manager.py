# -*- coding: utf-8 -*-
"""
异步对话管理器（重构版）
整合 ASR + LLM + TTS 实现完整对话流程，支持流式打断
"""

import asyncio
import contextlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, Dict

from ..log import log
from .adapters import AsyncASRAdapter, AsyncLLMAdapter, AsyncTTSAdapter


class ConversationState(Enum):
    """对话状态"""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    PAUSED = "paused"


@dataclass
class ConversationConfig:
    """对话配置"""
    asr_model_dir: str = None
    asr_provider: str = "funasr"
    asr_device: str = "auto"
    asr_stream_profile: str = "balanced"
    tts_remote_url: str = None
    tts_spk_id: str = "玲"
    tts_enable_cache: bool = True
    tts_cache_size: int = 100
    user_id: str = "default_user"
    use_vad: bool = True
    use_text_input: bool = False
    silence_duration: float = 0.55
    enable_barge_in: bool = True


class AsyncConversationManager:
    """异步对话管理器"""

    def __init__(self, config: ConversationConfig):
        self.config = config
        self.state = ConversationState.IDLE
        self._callbacks: Dict[str, Callable] = {}
        self._current_task: Optional[asyncio.Task] = None
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._asr: Optional[AsyncASRAdapter] = None
        self._llm: Optional[AsyncLLMAdapter] = None
        self._tts: Optional[AsyncTTSAdapter] = None

    def set_callbacks(self, **callbacks):
        """设置回调函数"""
        self._callbacks.update(callbacks)

    def _trigger_callback(self, callback_name: str, *args, **kwargs):
        """触发回调函数"""
        if callback_name in self._callbacks:
            try:
                self._callbacks[callback_name](*args, **kwargs)
            except Exception as e:
                log.error(f"回调 {callback_name} 执行失败: {e}")

    def _update_state(self, new_state: ConversationState):
        """更新对话状态"""
        old_state = self.state
        self.state = new_state
        log.debug(f"状态切换: {old_state.value} -> {new_state.value}")
        self._trigger_callback("on_state_change", new_state)

    async def run_async(self):
        """运行异步对话系统（主循环）"""
        log.info("异步对话系统已启动")
        while not self._stop_event.is_set():
            try:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._stop_event.wait(), timeout=0.1)
            except asyncio.CancelledError:
                break
        log.info("异步对话系统已停止")

    async def stop(self):
        """停止对话系统"""
        self._stop_event.set()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._current_task

    async def process_audio(self, audio_data):
        """
        处理音频输入

        Args:
            audio_data: 音频数据
        """
        log.info(f"处理音频输入，长度: {len(audio_data)}")

        try:
            # 更新状态
            self._update_state(ConversationState.LISTENING)

            # 调用 ASR 转录
            text = await self._asr.transcribe(audio_data)

            if not text:
                log.debug("ASR 未识别到文本")
                self._update_state(ConversationState.IDLE)
                return

            log.info(f"ASR 识别结果: {text}")

            # 处理识别的文本
            await self.process_text(text)

        except asyncio.CancelledError:
            log.info("音频处理被取消")
            self._update_state(ConversationState.IDLE)
            raise
        except Exception as e:
            log.error(f"音频处理失败: {e}")
            self._update_state(ConversationState.IDLE)
            raise

    async def process_text(self, text: str):
        """处理文本输入"""
        log.info(f"处理文本输入: {text}")

        try:
            # 更新状态
            self._update_state(ConversationState.PROCESSING)

            # 调用 LLM 生成回复
            messages = [{"role": "user", "content": text}]
            response = await self._llm.chat(messages)

            # 触发字幕回调
            self._trigger_callback("on_subtitle", response, True, "neutral")

            # 调用 TTS 合成语音
            audio_data = await self._tts.synthesize(response)

            # 更新状态
            self._update_state(ConversationState.IDLE)

        except asyncio.CancelledError:
            log.info("文本处理被取消")
            self._update_state(ConversationState.IDLE)
            raise
        except Exception as e:
            log.error(f"文本处理失败: {e}")
            self._update_state(ConversationState.IDLE)
            raise

    async def cancel_current_turn(self):
        """取消当前对话轮次"""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass
            log.info("当前对话轮次已取消")

        self._update_state(ConversationState.IDLE)
