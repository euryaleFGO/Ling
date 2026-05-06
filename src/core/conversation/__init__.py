# -*- coding: utf-8 -*-
"""
对话模块

提供对话状态管理、句子切分等核心功能。

子模块：
  - state:           对话状态枚举、配置数据类、性能指标
  - sentence_splitter: 智能句子切分（用于 TTS 流式合成）
"""

from .state import ConversationState, ConversationConfig, TurnMetrics
from .sentence_splitter import pop_sentence, split_sentences

__all__ = [
    # 数据类
    "ConversationState",
    "ConversationConfig",
    "TurnMetrics",
    # 句子切分
    "pop_sentence",
    "split_sentences",
]
