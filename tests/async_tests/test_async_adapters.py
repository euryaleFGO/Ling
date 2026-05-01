# tests/unit/test_async_adapters.py
import pytest
import numpy as np
from typing import List, Dict
from unittest.mock import Mock
from src.core.async_core.adapters import AsyncAdapter, AsyncASRAdapter


def test_import_async_adapter():
    """测试可以导入 AsyncAdapter"""
    assert AsyncAdapter is not None


def test_async_adapter_initialization():
    """测试 AsyncAdapter 初始化"""
    mock_engine = Mock()
    adapter = AsyncAdapter(mock_engine)

    assert adapter._sync_engine == mock_engine


@pytest.mark.asyncio
async def test_async_adapter_run_sync():
    """测试 AsyncAdapter 的 _run_sync 方法"""
    def sync_method(x, y):
        return x + y

    mock_engine = Mock()
    adapter = AsyncAdapter(mock_engine)

    result = await adapter._run_sync(sync_method, 1, 2)

    assert result == 3


class MockASR:
    """模拟 ASR 引擎"""
    def transcribe(self, audio_data: np.ndarray) -> str:
        return "transcribed text"


@pytest.mark.asyncio
async def test_async_asr_transcribe():
    """测试 ASR 异步转录"""
    mock_asr = MockASR()
    adapter = AsyncASRAdapter(mock_asr)

    audio_data = np.random.randn(16000)
    result = await adapter.transcribe(audio_data)

    assert isinstance(result, str)
    assert result == "transcribed text"


class MockLLM:
    """模拟 LLM 引擎"""
    def chat(self, messages: List[Dict]) -> str:
        return "LLM response"


@pytest.mark.asyncio
async def test_async_llm_chat():
    """测试 LLM 异步聊天"""
    from src.core.async_core.adapters import AsyncLLMAdapter

    mock_llm = MockLLM()
    adapter = AsyncLLMAdapter(mock_llm)

    messages = [{"role": "user", "content": "Hello"}]
    result = await adapter.chat(messages)

    assert isinstance(result, str)
    assert result == "LLM response"


class MockTTS:
    """模拟 TTS 引擎"""
    def synthesize(self, text: str) -> np.ndarray:
        return np.random.randn(16000)

@pytest.mark.asyncio
async def test_async_tts_synthesize():
    """测试 TTS 异步合成"""
    from src.core.async_core.adapters import AsyncTTSAdapter

    mock_tts = MockTTS()
    adapter = AsyncTTSAdapter(mock_tts)

    result = await adapter.synthesize("Hello world")

    assert isinstance(result, np.ndarray)
    assert result.shape == (16000,)
