# -*- coding: utf-8 -*-
"""
对话模块

提供对话状态管理、句子切分、ASR/TTS/音频处理等核心功能。

从 conversation_manager.py 拆分后的模块组织：
  - state:           对话状态枚举、配置数据类、性能指标
  - sentence_splitter: 智能句子切分（用于 TTS 流式合成）
  - asr_handler:     ASR 初始化、监听、流式合并、SV/SER/PUNC/说话人识别
  - tts_handler:     TTS 初始化、语音合成播放、口型同步
  - audio_handler:   音频设备初始化、流式打断（Barge-in）
"""

from .state import ConversationState, ConversationConfig, TurnMetrics
from .sentence_splitter import pop_sentence, split_sentences
from .asr_handler import ASRHandler
from .tts_handler import TTSHandler
from .audio_handler import AudioHandler

__all__ = [
    # 数据类
    "ConversationState",
    "ConversationConfig",
    "TurnMetrics",
    # 句子切分
    "pop_sentence",
    "split_sentences",
    # Mixin 处理器
    "ASRHandler",
    "TTSHandler",
    "AudioHandler",
]
