"""
简谱解析器

将数字简谱（如 "1 1 2 2 3 3 2 -"）转换为 DiffSinger DS 格式所需的
音符序列、时值序列等。
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# 数字简谱 → MIDI 音符映射（C大调）
# 1=Do, 2=Re, 3=Mi, 4=Fa, 5=Sol, 6=La, 7=Si
NOTE_MAP_BASE = {
    '1': 'C', '2': 'D', '3': 'E', '4': 'F',
    '5': 'G', '6': 'A', '7': 'B',
}

# 调号偏移（半音数）
KEY_OFFSET = {
    'C': 0, 'Db': 1, 'D': 2, 'Eb': 3, 'E': 4, 'F': 5,
    'Gb': 6, 'G': 7, 'Ab': 8, 'A': 9, 'Bb': 10, 'B': 11,
    'C#': 1, 'D#': 3, 'F#': 6, 'G#': 8, 'A#': 10,
}

# MIDI 音符名称
MIDI_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def _midi_note_name(midi_num: int) -> str:
    """MIDI 编号转音符名称，如 60 → C4"""
    octave = (midi_num // 12) - 1
    note = MIDI_NOTE_NAMES[midi_num % 12]
    return f"{note}{octave}"


@dataclass
class NotationResult:
    """简谱解析结果"""
    note_seq: str          # 空格分隔的音符序列，如 "C4 C4 D4 D4 E4 E4 D4"
    note_dur: str          # 空格分隔的时值序列（秒），如 "0.5 0.5 0.5 0.5 0.5 0.5 1.0"
    note_slur: str         # 连音标记，如 "0 0 0 0 0 0 0"
    lyrics: str            # 空格分隔的歌词字（用于音素转换）
    total_duration: float  # 总时长（秒）


def parse_notation(
    notation: str,
    lyrics: str = "",
    key: str = "C",
    tempo: int = 120,
    beat_unit: float = 0.5,
) -> NotationResult:
    """
    解析数字简谱为 DiffSinger 格式

    Args:
        notation: 数字简谱，格式如 "1 1 2 2 3 3 2 - | 1 1 2 2 3 3 2 -"
                  支持：1-7（音符），0/-（休止），.（低音），'（高音）
                  时值：无后缀=1拍，-=2拍，~=延长，附点用.表示
        lyrics: 对应歌词，如 "两只老虎两只老虎"
        key: 调号，如 "C", "G", "D"
        tempo: 速度 BPM（每分钟拍数）
        beat_unit: 一拍的时长（秒），默认 0.5（即 120 BPM）

    Returns:
        NotationResult
    """
    # 计算实际一拍时长
    if tempo > 0:
        beat_duration = 60.0 / tempo
    else:
        beat_duration = beat_unit

    # 获取调号偏移
    key_semitones = KEY_OFFSET.get(key, 0)

    # 清理输入：去掉小节线，分割音符
    notation_clean = notation.replace('|', '').strip()
    tokens = notation_clean.split()

    # 解析歌词：按字分割
    lyric_chars = list(lyrics.replace(' ', '').replace('|', '')) if lyrics else []

    notes = []       # (midi_num, duration_beats, is_rest, is_slur)
    current_octave = 4  # 默认中音区

    for token in tokens:
        # 解析音符
        note_char = None
        octave_shift = 0
        duration_beats = 1.0
        is_rest = False
        is_slur = False

        # 提取音符主体
        if token in ('0', '-', '—'):
            is_rest = True
            note_char = 'rest'
        elif token[0] in '1234567':
            note_char = token[0]
            octave_shift = 0
        else:
            logger.warning(f"未知音符标记: {token}，跳过")
            continue

        # 解析八度标记
        remaining = token[1:] if note_char and note_char != 'rest' else ''
        for ch in remaining:
            if ch == '.':
                octave_shift -= 1  # 低音点
            elif ch == "'":
                octave_shift += 1  # 高音点

        # 解析时值标记
        for ch in remaining:
            if ch == '-':
                duration_beats += 1.0  # 每个 - 增加一拍
            elif ch == '~':
                duration_beats += 0.5  # 延长半拍
            elif ch == '.':
                # 附点（如果在时值部分）
                pass  # 已在八度部分处理

        # 计算 MIDI 音符
        if is_rest:
            midi_num = 0
        else:
            base_note = NOTE_MAP_BASE.get(note_char, 'C')
            base_midi = MIDI_NOTE_NAMES.index(base_note) + key_semitones
            midi_num = 60 + base_midi + (octave_shift * 12)  # C4 = 60

        notes.append((midi_num, duration_beats, is_rest, is_slur))

    if not notes:
        logger.warning("简谱解析结果为空")
        return NotationResult(
            note_seq="rest",
            note_dur=str(beat_duration),
            note_slur="0",
            lyrics="",
            total_duration=beat_duration,
        )

    # 构建输出序列
    note_seq_parts = []
    note_dur_parts = []
    slur_parts = []
    total_duration = 0.0

    for midi_num, dur_beats, is_rest, is_slur in notes:
        duration_sec = dur_beats * beat_duration

        if is_rest:
            note_seq_parts.append("rest")
        else:
            note_seq_parts.append(_midi_note_name(midi_num))

        note_dur_parts.append(f"{duration_sec:.4f}")
        slur_parts.append("1" if is_slur else "0")
        total_duration += duration_sec

    # 对齐歌词和音符
    lyric_list = lyric_chars[:len(note_seq_parts)] if lyric_chars else []
    # 用空字符串补齐
    while len(lyric_list) < len(note_seq_parts):
        lyric_list.append("")

    return NotationResult(
        note_seq=" ".join(note_seq_parts),
        note_dur=" ".join(note_dur_parts),
        note_slur=" ".join(slur_parts),
        lyrics=" ".join(lyric_list),
        total_duration=total_duration,
    )
