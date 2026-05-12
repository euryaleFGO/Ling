"""
歌曲标签解析器

解析 LLM 输出中的 <sing> 标签，将混合文本拆分为说话和唱歌部分。
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SingingPart:
    """歌曲片段"""
    mode: str           # "speak" 或 "sing"
    content: str        # 文本内容（说话文本 或 歌词）
    key: str = "C"      # 调号（仅唱歌模式）
    tempo: int = 120    # 速度 BPM（仅唱歌模式）
    style: str = ""     # 风格（仅唱歌模式）
    notation: str = ""  # 简谱（仅唱歌模式，可选）
    song_name: str = "" # 预设歌曲名（仅唱歌模式，可选）


# <sing> 标签正则
# 支持格式：
#   <sing>歌词</sing>
#   <sing key=C tempo=120>歌词</sing>
#   <sing name="两只老虎">歌词</sing>
_SING_PATTERN = re.compile(
    r'<sing\s*([^>]*)>(.*?)</sing>',
    re.DOTALL | re.IGNORECASE
)

# 标签属性解析
_ATTR_PATTERN = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))')


def _parse_attributes(attr_str: str) -> dict:
    """解析标签属性"""
    attrs = {}
    for match in _ATTR_PATTERN.finditer(attr_str):
        key = match.group(1)
        value = match.group(2) or match.group(3) or match.group(4)
        attrs[key.lower()] = value
    return attrs


def parse_singing_tags(text: str) -> List[SingingPart]:
    """
    解析文本中的 <sing> 标签

    Args:
        text: 包含 <sing> 标签的完整文本

    Returns:
        SingingPart 列表，按顺序排列

    示例：
        >>> parts = parse_singing_tags("你好<sing>两只老虎</sing>再见")
        >>> # [
        >>> #   SingingPart(mode="speak", content="你好"),
        >>> #   SingingPart(mode="sing", content="两只老虎"),
        >>> #   SingingPart(mode="speak", content="再见"),
        >>> # ]
    """
    parts = []
    last_end = 0

    for match in _SING_PATTERN.finditer(text):
        # 标签前的说话文本
        before = text[last_end:match.start()].strip()
        if before:
            parts.append(SingingPart(mode="speak", content=before))

        # 解析标签属性
        attrs = _parse_attributes(match.group(1))

        # 歌词内容
        lyrics = match.group(2).strip()

        singing_part = SingingPart(
            mode="sing",
            content=lyrics,
            key=attrs.get('key', 'C'),
            tempo=int(attrs.get('tempo', '120')),
            style=attrs.get('style', ''),
            notation=attrs.get('notation', ''),
            song_name=attrs.get('name', attrs.get('song', '')),
        )
        parts.append(singing_part)

        last_end = match.end()

    # 标签后的说话文本
    after = text[last_end:].strip()
    if after:
        parts.append(SingingPart(mode="speak", content=after))

    # 如果没有找到任何标签，整个文本作为说话
    if not parts:
        parts.append(SingingPart(mode="speak", content=text))

    return parts


def has_singing_tag(text: str) -> bool:
    """检查文本是否包含 <sing> 标签"""
    return bool(_SING_PATTERN.search(text))


def extract_singing_lyrics(text: str) -> List[str]:
    """提取所有 <sing> 标签中的歌词"""
    return [match.group(2).strip() for match in _SING_PATTERN.finditer(text)]
