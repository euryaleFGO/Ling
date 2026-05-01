# src/core/async_adapters.py
# -*- coding: utf-8 -*-
"""
异步适配器层
将同步引擎包装为异步接口，使用 asyncio.to_thread() 实现
"""

import asyncio
from typing import Any, Callable, List, Dict

import numpy as np


class AsyncAdapter:
    """异步适配器基类"""

    def __init__(self, sync_engine: Any):
        """
        初始化异步适配器

        Args:
            sync_engine: 同步引擎实例
        """
        self._sync_engine = sync_engine

    async def _run_sync(self, method: Callable, *args, **kwargs) -> Any:
        """
        运行同步方法（异步包装）

        Args:
            method: 要执行的同步方法
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            方法执行结果
        """
        return await asyncio.to_thread(method, *args, **kwargs)


class AsyncASRAdapter(AsyncAdapter):
    """ASR 异步适配器"""

    async def transcribe(self, audio_data: np.ndarray) -> str:
        """
        异步转录音频

        Args:
            audio_data: 音频数据 (numpy array)

        Returns:
            转录文本
        """
        return await self._run_sync(self._sync_engine.transcribe, audio_data)


class AsyncLLMAdapter(AsyncAdapter):
    """LLM 异步适配器"""

    async def chat(self, messages: List[Dict]) -> str:
        """
        异步聊天

        Args:
            messages: 消息列表

        Returns:
            LLM 回复
        """
        return await self._run_sync(self._sync_engine.chat, messages)


class AsyncTTSAdapter(AsyncAdapter):
    """TTS 异步适配器"""

    async def synthesize(self, text: str) -> np.ndarray:
        """
        异步合成语音

        Args:
            text: 要合成的文本

        Returns:
            音频数据 (numpy array)
        """
        return await self._run_sync(self._sync_engine.synthesize, text)
