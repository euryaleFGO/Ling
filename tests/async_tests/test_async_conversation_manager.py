import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock

def test_import_async_conversation_manager():
    """测试可以导入 AsyncConversationManager"""
    from src.core.async_core.conversation_manager import AsyncConversationManager
    assert AsyncConversationManager is not None

def test_conversation_state_enum():
    """测试 ConversationState 枚举"""
    from src.core.async_core.conversation_manager import ConversationState

    assert ConversationState.IDLE.value == "idle"
    assert ConversationState.LISTENING.value == "listening"
    assert ConversationState.PROCESSING.value == "processing"
    assert ConversationState.SPEAKING.value == "speaking"
    assert ConversationState.PAUSED.value == "paused"

def test_async_conversation_manager_initialization():
    """测试 AsyncConversationManager 初始化"""
    from src.core.async_core.conversation_manager import AsyncConversationManager, ConversationConfig, ConversationState

    config = ConversationConfig()
    manager = AsyncConversationManager(config)

    assert manager.config == config
    assert manager.state == ConversationState.IDLE
    assert manager._callbacks == {}


import numpy as np

class MockASREngine:
    async def transcribe(self, audio_data):
        return "用户说：你好"

class MockLLMEngine:
    async def chat(self, messages):
        return "你好！有什么我可以帮助你的吗？"

class MockTTSEngine:
    async def synthesize(self, text):
        return np.random.randn(16000)

def test_process_audio_flow():
    """测试音频处理流程"""
    from src.core.async_core.conversation_manager import AsyncConversationManager, ConversationConfig, ConversationState

    config = ConversationConfig()
    manager = AsyncConversationManager(config)

    # 设置模拟引擎
    manager._asr = MockASREngine()
    manager._llm = MockLLMEngine()
    manager._tts = MockTTSEngine()

    # 处理音频
    audio_data = np.random.randn(16000)
    asyncio.run(manager.process_audio(audio_data))

    # 验证状态
    assert manager.state == ConversationState.IDLE


def test_cancel_current_turn():
    """测试取消当前对话轮次"""
    from src.core.async_core.conversation_manager import AsyncConversationManager, ConversationConfig, ConversationState

    async def _run_test():
        config = ConversationConfig()
        manager = AsyncConversationManager(config)

        # 设置模拟引擎
        manager._asr = MockASREngine()
        manager._llm = MockLLMEngine()
        manager._tts = MockTTSEngine()

        # 创建一个长时间运行的任务
        async def long_running_task():
            manager._update_state(ConversationState.PROCESSING)
            await asyncio.sleep(10)

        manager._current_task = asyncio.create_task(long_running_task())
        # 给任务一点时间启动
        await asyncio.sleep(0.01)

        # 取消任务
        await manager.cancel_current_turn()

        # 验证状态
        assert manager.state == ConversationState.IDLE

    asyncio.run(_run_test())


def test_process_text_flow():
    """测试文本处理流程"""
    from src.core.async_core.conversation_manager import AsyncConversationManager, ConversationConfig, ConversationState

    config = ConversationConfig()
    manager = AsyncConversationManager(config)

    # 设置模拟引擎
    manager._asr = MockASREngine()
    manager._llm = MockLLMEngine()
    manager._tts = MockTTSEngine()

    # 设置回调
    callback_results = []
    def on_subtitle(text, is_final, emotion="neutral"):
        callback_results.append({"text": text, "is_final": is_final})

    manager.set_callbacks(on_subtitle=on_subtitle)

    # 处理文本
    asyncio.run(manager.process_text("你好"))

    # 验证状态
    assert manager.state == ConversationState.IDLE
