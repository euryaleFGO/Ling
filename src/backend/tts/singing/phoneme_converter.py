"""
中文歌词 → DiffSinger 音素转换器

将中文歌词转换为 DiffSinger 所需的音素序列 (ph_seq) 和音素时值 (ph_dur)。
基于 opencpop 音素表（DiffSinger 中文标准）。
"""

import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

# 尝试导入 pypinyin，如果不可用则使用简化映射
try:
    from pypinyin import pypinyin, Style
    HAS_PYPINYIN = True
except ImportError:
    HAS_PYPINYIN = False
    logger.warning("pypinyin 未安装，将使用简化拼音映射。安装: pip install pypinyin")


# opencpop 声母表 (21个)
INITIALS = [
    'b', 'p', 'm', 'f', 'd', 't', 'n', 'l',
    'g', 'k', 'h', 'j', 'q', 'x',
    'zh', 'ch', 'sh', 'r', 'z', 'c', 's',
]

# opencpop 韵母表 (36个)
FINALS = [
    'a', 'o', 'e', 'i', 'u', 'v', 'er',
    'ai', 'ei', 'ao', 'ou',
    'an', 'en', 'ang', 'eng', 'ong',
    'ia', 'ie', 'iao', 'iou', 'ian', 'in', 'iang', 'ing', 'iong',
    'ua', 'uo', 'uai', 'uei', 'uan', 'uen', 'uang', 'ueng',
    've', 'van', 'vn',
]

# 简化拼音映射（无 pypinyin 时使用）
SIMPLE_PINYIN_MAP = {
    '两': [('l', 'iang')],
    '只': [('zh', 'i')],
    '老': [('l', 'ao')],
    '虎': [('h', 'u')],
    '跑': [('p', 'ao')],
    '得': [('d', 'e')],
    '快': [('k', 'uai')],
    '一': [('y', 'i')],
    '没': [('m', 'ei')],
    '有': [('y', 'iou')],
    '眼': [('y', 'an')],
    '睛': [('j', 'ing')],
    '尾': [('w', 'ei')],
    '巴': [('b', 'a')],
    '真': [('zh', 'en')],
    '奇': [('q', 'i')],
    '怪': [('g', 'uai')],
    '你': [('n', 'i')],
    '好': [('h', 'ao')],
    '天': [('t', 'ian')],
    '气': [('q', 'i')],
    '今': [('j', 'in')],
    '小': [('x', 'iao')],
    '星': [('x', 'ing')],
    '星': [('x', 'ing')],
    '生': [('sh', 'eng')],
    '日': [('r', 'i')],
    '快': [('k', 'uai')],
    '乐': [('l', 'e')],
    '爱': [('y', 'ai')],
    '世': [('sh', 'i')],
    '界': [('j', 'ie')],
}

# 特殊拼音→音素映射（opencpop 标准）
PINYIN_TO_PHONEME = {
    'ju': 'j v',
    'qu': 'q v',
    'xu': 'x v',
    'ju': 'j v',
    'lü': 'l v',
    'nü': 'n v',
    'zhi': 'zh ir',
    'chi': 'ch ir',
    'shi': 'sh ir',
    'ri': 'r ir',
    'zi': 'z ii',
    'ci': 'c ii',
    'si': 's ii',
}


def _pinyin_to_phonemes(pinyin_initial: str, pinyin_final: str) -> List[str]:
    """
    将声母韵母转换为 DiffSinger 音素序列

    Args:
        pinyin_initial: 声母（如 "zh", "l", ""）
        pinyin_final: 韵母（如 "iang", "ao", "i"）

    Returns:
        音素列表，如 ['zh', 'ir'] 或 ['l', 'iang']
    """
    # 检查特殊映射
    full_pinyin = pinyin_initial + pinyin_final
    if full_pinyin in PINYIN_TO_PHONEME:
        return PINYIN_TO_PHONEME[full_pinyin].split()

    phonemes = []
    if pinyin_initial:
        phonemes.append(pinyin_initial)
    if pinyin_final:
        phonemes.append(pinyin_final)

    return phonemes if phonemes else ['AP']  # AP = 呼吸音


def _char_to_pinyin(char: str) -> List[Tuple[str, str]]:
    """
    单个汉字转拼音（声母, 韵母）

    Returns:
        [(initial, final), ...] 如 [('zh', 'iang')]
    """
    if HAS_PYPINYIN:
        result = pypinyin(char, style=Style.INITIALS, strict=False)
        initials = result[0] if result else ['']
        result2 = pypinyin(char, style=Style.FINALS, strict=False)
        finals = result2[0] if result2 else ['']

        pairs = []
        for ini, fin in zip(initials, finals):
            pairs.append((ini or '', fin or ''))
        return pairs if pairs else [('', '')]
    else:
        # 简化映射
        if char in SIMPLE_PINYIN_MAP:
            return SIMPLE_PINYIN_MAP[char]
        # 未知字符返回空
        return [('', '')]


def convert_to_phonemes(
    lyrics: str,
    note_seq: str,
    note_dur: str,
    note_slur: str = "",
) -> Tuple[str, str, str, str]:
    """
    将歌词转换为 DiffSinger 音素序列

    Args:
        lyrics: 歌词文本（空格分隔的字），如 "两只老虎"
        note_seq: 音符序列，如 "C4 C4 D4 D4"
        note_dur: 音符时值，如 "0.5 0.5 0.5 0.5"
        note_slur: 连音标记

    Returns:
        (ph_seq, ph_dur, ph_num, text) 元组：
        - ph_seq: 空格分隔的音素序列
        - ph_dur: 空格分隔的音素时值
        - ph_num: 每个字的音素数量
        - text: 文本标注
    """
    lyric_list = lyrics.split()
    note_list = note_seq.split()
    dur_list = note_dur.split()

    # 对齐：取较短的长度
    n = min(len(lyric_list), len(note_list), len(dur_list))

    all_phonemes = []
    all_durations = []
    ph_nums = []
    text_parts = []

    for i in range(n):
        char = lyric_list[i] if i < len(lyric_list) else ''
        duration = float(dur_list[i]) if i < len(dur_list) else 0.5

        if not char or char in ('-', '—', '0', 'rest'):
            # 休止符
            all_phonemes.append('SP')  # SP = 停顿
            all_durations.append(f"{duration:.4f}")
            ph_nums.append('1')
            text_parts.append('SP')
            continue

        # 汉字转拼音→音素
        pinyin_pairs = _char_to_pinyin(char)
        if pinyin_pairs:
            ini, fin = pinyin_pairs[0]
            phonemes = _pinyin_to_phonemes(ini, fin)
        else:
            phonemes = ['AP']

        # 分配时值给每个音素
        n_ph = len(phonemes)
        ph_dur_each = duration / n_ph if n_ph > 0 else duration

        for ph in phonemes:
            all_phonemes.append(ph)
            all_durations.append(f"{ph_dur_each:.4f}")

        ph_nums.append(str(n_ph))
        text_parts.append(char)

    # 在每个字之间插入 SP（停顿）
    final_phonemes = []
    final_durations = []
    final_ph_nums = []
    final_text = []

    for i in range(len(ph_nums)):
        n_ph = int(ph_nums[i])
        start_idx = sum(int(x) for x in final_ph_nums)
        for j in range(n_ph):
            idx = start_idx + j
            if idx < len(all_phonemes):
                final_phonemes.append(all_phonemes[idx])
                final_durations.append(all_durations[idx])

        final_ph_nums.append(ph_nums[i])
        if i < len(text_parts):
            final_text.append(text_parts[i])

    ph_seq = " ".join(final_phonemes)
    ph_dur = " ".join(final_durations)
    ph_num = " ".join(final_ph_nums)
    text = " ".join(final_text)

    return ph_seq, ph_dur, ph_num, text
