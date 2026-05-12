"""
预设歌曲库

内置常见中文歌曲的简谱数据，用于直接调用演唱。
"""

import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# 预设歌曲数据
# 格式：
#   lyrics: 歌词（用 | 分隔小节）
#   notes: 数字简谱（用 | 分隔小节）
#   key: 调号
#   tempo: 速度 BPM
PRESET_SONGS: Dict[str, Dict] = {
    "两只老虎": {
        "lyrics": "两只老虎 两只老虎 跑得快 跑得快 一只没有眼睛 一只没有尾巴 真奇怪 真奇怪",
        "notes": "1 1 2 2 3 3 2 - 1 1 2 2 3 3 2 -",
        "key": "C",
        "tempo": 120,
        "description": "经典儿歌",
    },
    "小星星": {
        "lyrics": "一闪一闪亮晶晶 满天都是小星星 挂在天上放光明 好像许多小眼睛",
        "notes": "1 1 5 5 6 6 5 - 4 4 3 3 2 2 1 - 5 5 4 4 3 3 2 - 5 5 4 4 3 3 2 -",
        "key": "C",
        "tempo": 100,
        "description": "经典儿歌 Twinkle Twinkle",
    },
    "生日快乐": {
        "lyrics": "祝你生日快乐 祝你生日快乐 祝你生日快乐 祝你生日快乐",
        "notes": "1 1 2 1 4 3 - 1 1 2 1 5 4 - 1 1 8 6 4 3 2 - 7 7 6 4 5 4 -",
        "key": "C",
        "tempo": 110,
        "description": "生日歌",
    },
    "新年好": {
        "lyrics": "新年好呀 新年好呀 祝贺大家新年好 我们唱歌 我们跳舞 祝贺大家新年好",
        "notes": "3 3 3 1 5 5 5 3 3 5 5 3 2 1 2 - 3 5 5 3 2 2 3 2 1 -",
        "key": "C",
        "tempo": 120,
        "description": "新年歌曲",
    },
    "茉莉花": {
        "lyrics": "好一朵美丽的茉莉花 好一朵美丽的茉莉花 芬芳美丽满枝桠 又香又白人人夸",
        "notes": "3 3 5 6 1' 6 5 6 5 3 5 3 2 1 1 2 3 3 5 6 1' 6 5 6 5 3 5 3 2 1 1 2",
        "key": "C",
        "tempo": 80,
        "description": "中国民歌",
    },
    "送别": {
        "lyrics": "长亭外 古道边 芳草碧连天 晚风拂柳笛声残 夕阳山外山",
        "notes": "5 3 5 1' 6 5 3 5 2 1 6 1 5 - 5 3 5 1' 6 5 3 5 2 1 6 1 1 -",
        "key": "C",
        "tempo": 72,
        "description": "经典歌曲",
    },
    "虫儿飞": {
        "lyrics": "虫儿飞 虫儿飞 你在思念谁 天上的星星流泪 地上的玫瑰枯萎",
        "notes": "3 3 3 2 1 2 3 - 3 3 3 2 1 2 1 - 6 6 6 5 3 5 6 - 5 5 5 3 2 3 5 -",
        "key": "C",
        "tempo": 85,
        "description": "儿歌",
    },
    "世上只有妈妈好": {
        "lyrics": "世上只有妈妈好 有妈的孩子像块宝 投进妈妈的怀抱 幸福享不了",
        "notes": "6 6 1' 6 5 3 5 - 6 6 1' 6 5 3 2 - 3 3 5 6 5 3 2 1 6 1 2 1 -",
        "key": "C",
        "tempo": 90,
        "description": "经典儿歌",
    },
}


def get_preset_song(name: str) -> Optional[Dict]:
    """
    获取预设歌曲数据

    Args:
        name: 歌曲名称（模糊匹配）

    Returns:
        歌曲数据字典，未找到返回 None
    """
    # 精确匹配
    if name in PRESET_SONGS:
        return PRESET_SONGS[name].copy()

    # 模糊匹配
    for song_name, song_data in PRESET_SONGS.items():
        if name in song_name or song_name in name:
            return song_data.copy()

    return None


def list_preset_songs() -> List[Dict]:
    """
    列出所有预设歌曲

    Returns:
        歌曲信息列表
    """
    return [
        {
            "name": name,
            "description": data.get("description", ""),
            "key": data.get("key", "C"),
            "tempo": data.get("tempo", 120),
        }
        for name, data in PRESET_SONGS.items()
    ]


def add_preset_song(
    name: str,
    lyrics: str,
    notes: str,
    key: str = "C",
    tempo: int = 120,
    description: str = "",
):
    """
    添加预设歌曲（运行时）

    Args:
        name: 歌曲名称
        lyrics: 歌词
        notes: 数字简谱
        key: 调号
        tempo: 速度
        description: 描述
    """
    PRESET_SONGS[name] = {
        "lyrics": lyrics,
        "notes": notes,
        "key": key,
        "tempo": tempo,
        "description": description,
    }
    logger.info(f"添加预设歌曲: {name}")
