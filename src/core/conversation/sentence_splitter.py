# -*- coding: utf-8 -*-
"""
句子切分模块

实现智能句子切分（硬切 + 软切），用于 TTS 流式合成
"""

import re
from typing import Tuple, Optional


# 硬切：句号、问号、感叹号、换行
_SENTENCE_END = re.compile(r"[。！？.!?\n]")

# 最小句子长度（避免单字污染 TTS）
_MIN_SENTENCE_CHARS = 2

# 软切：超过 18 字在逗号/分号处切
_SOFT_BREAK = re.compile(r"[，、；,;]")
_SOFT_BREAK_AFTER = 18


def pop_sentence(buf: str) -> Tuple[Optional[str], str]:
    """
    从 buf 头部切出一句话；切不出来就原样返回。

    硬切：。！？.!?\n
    软切：buf 长度超过 _SOFT_BREAK_AFTER 时在逗号/分号处切

    Args:
        buf: 待切分的文本缓冲区

    Returns:
        (sentence, remaining) - 切出的句子和剩余文本
    """
    match = _SENTENCE_END.search(buf)
    if match is not None:
        end = match.end()
        sentence = buf[:end]
        if len(sentence.strip()) < _MIN_SENTENCE_CHARS:
            return None, buf
        return sentence, buf[end:]

    if len(buf) >= _SOFT_BREAK_AFTER:
        soft = _SOFT_BREAK.search(buf)
        if soft is not None:
            end = soft.end()
            sentence = buf[:end]
            if len(sentence.strip()) >= _MIN_SENTENCE_CHARS:
                return sentence, buf[end:]

    return None, buf


def split_sentences(text: str) -> list[str]:
    """
    将文本切分为句子列表

    Args:
        text: 输入文本

    Returns:
        句子列表
    """
    sentences = []
    remaining = text

    while remaining:
        sentence, remaining = pop_sentence(remaining)
        if sentence is None:
            # 没有更多可切分的句子，将剩余文本作为最后一句
            if remaining.strip():
                sentences.append(remaining)
            break
        sentences.append(sentence)

    return sentences
