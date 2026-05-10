# -*- coding: utf-8 -*-
"""
TTS Engine 模块
提供 CosyVoice2 实时语音合成和 DiffSinger 歌声合成功能
"""

from .tts_engine import CosyvoiceRealTimeTTS, fade_in_out
from .singing_engine import DiffSingerEngine

__all__ = ['CosyvoiceRealTimeTTS', 'fade_in_out', 'DiffSingerEngine']
