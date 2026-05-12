"""
歌声合成模块

基于 DiffSinger 的歌声合成 (SVS) 子系统，
支持简谱输入、中文歌词、预设歌曲。
"""

from .notation_parser import parse_notation, NotationResult
from .phoneme_converter import convert_to_phonemes
from .song_tag_parser import parse_singing_tags, SingingPart
from .preset_songs import get_preset_song, list_preset_songs

__all__ = [
    "parse_notation",
    "NotationResult",
    "convert_to_phonemes",
    "parse_singing_tags",
    "SingingPart",
    "get_preset_song",
    "list_preset_songs",
]
