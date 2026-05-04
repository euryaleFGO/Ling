# -*- coding: utf-8 -*-
"""
对话模块

提供对话状态管理、句子切分等核心功能
"""

from .state import ConversationState, ConversationConfig, TurnMetrics
from .sentence_splitter import pop_sentence, split_sentences

__all__ = [
    "ConversationState",
    "ConversationConfig",
    "TurnMetrics",
    "pop_sentence",
    "split_sentences",
]
