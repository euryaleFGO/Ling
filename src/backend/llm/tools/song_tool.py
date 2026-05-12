"""
歌曲工具

让 Agent 能够触发唱歌功能，支持：
1. 预设歌曲直接演唱
2. 自定义歌词 + 简谱演唱
3. 列出可用歌曲
"""

import json
import logging
from typing import List

from .base_tool import BaseTool, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class SongTool(BaseTool):
    """歌曲演唱工具"""

    @property
    def name(self) -> str:
        return "sing_song"

    @property
    def description(self) -> str:
        return (
            "唱一首歌。可以唱预设歌曲，也可以唱自定义歌词。"
            "当你想唱歌给用户听时使用此工具。"
            "注意：此工具需要歌声合成功能已启用（singing.enable=true）。"
        )

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型：'preset' 唱预设歌曲, 'custom' 唱自定义歌词, 'list' 列出可用歌曲",
                required=True,
                enum=["preset", "custom", "list"],
            ),
            ToolParameter(
                name="song_name",
                type="string",
                description="预设歌曲名称（action='preset' 时必填）",
                required=False,
            ),
            ToolParameter(
                name="lyrics",
                type="string",
                description="自定义歌词（action='custom' 时使用）",
                required=False,
            ),
            ToolParameter(
                name="notation",
                type="string",
                description="数字简谱，如 '1 1 2 2 3 3 2 -'（action='custom' 时使用）",
                required=False,
            ),
            ToolParameter(
                name="key",
                type="string",
                description="调号，如 C, G, D（默认 C）",
                required=False,
                default="C",
            ),
            ToolParameter(
                name="tempo",
                type="number",
                description="速度 BPM（默认 120）",
                required=False,
                default=120,
            ),
        ]

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "list")

        if action == "list":
            return self._list_songs()
        elif action == "preset":
            song_name = kwargs.get("song_name", "")
            if not song_name:
                return ToolResult(success=False, error="预设歌曲需要提供 song_name")
            return self._sing_preset(song_name)
        elif action == "custom":
            lyrics = kwargs.get("lyrics", "")
            notation = kwargs.get("notation", "")
            key = kwargs.get("key", "C")
            tempo = kwargs.get("tempo", 120)
            return self._sing_custom(lyrics, notation, key, tempo)
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")

    def _list_songs(self) -> ToolResult:
        """列出可用歌曲"""
        try:
            from backend.tts.singing.preset_songs import list_preset_songs  # noqa: absolute import for sys.path
            songs = list_preset_songs()
            if not songs:
                return ToolResult(
                    success=True,
                    data="暂无预设歌曲。你可以使用自定义歌词和简谱来唱歌。"
                )
            song_list = "\n".join(
                f"- {s['name']}（{s['description']}，{s['key']}调，{s['tempo']}BPM）"
                for s in songs
            )
            return ToolResult(
                success=True,
                data=f"可用预设歌曲：\n{song_list}\n\n使用示例：sing_song(action='preset', song_name='两只老虎')"
            )
        except Exception as e:
            return ToolResult(success=False, error=f"列出歌曲失败: {e}")

    def _sing_preset(self, song_name: str) -> ToolResult:
        """唱预设歌曲"""
        try:
            from backend.tts.singing.preset_songs import get_preset_song  # noqa: absolute import for sys.path
            song = get_preset_song(song_name)
            if not song:
                return ToolResult(
                    success=False,
                    error=f"未找到预设歌曲 '{song_name}'。请先用 action='list' 查看可用歌曲。"
                )

            # 返回标记文本，让 TTS pipeline 处理
            key = song.get("key", "C")
            tempo = song.get("tempo", 120)
            lyrics = song["lyrics"]
            notation = song["notes"]

            # 生成 <sing> 标签文本
            # Escape quotes in notation for XML attribute safety
            safe_notation = notation.replace('"', '&quot;').replace("'", '&apos;')
            sing_text = (
                f'<sing key={key} tempo={tempo} '
                f'notation="{safe_notation}">'
                f'{lyrics}'
                f'</sing>'
            )

            return ToolResult(
                success=True,
                data={
                    "action": "sing",
                    "text": sing_text,
                    "song_name": song_name,
                    "key": key,
                    "tempo": tempo,
                    "lyrics": lyrics,
                    "notation": notation,
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=f"唱预设歌曲失败: {e}")

    def _sing_custom(
        self,
        lyrics: str,
        notation: str,
        key: str = "C",
        tempo: int = 120,
    ) -> ToolResult:
        """唱自定义歌词"""
        if not lyrics:
            return ToolResult(success=False, error="歌词不能为空")

        try:
            # 生成 <sing> 标签文本
            if notation:
                safe_notation = notation.replace('"', '&quot;').replace("'", '&apos;')
                notation_attr = f' notation="{safe_notation}"'
            else:
                notation_attr = ""
            sing_text = f'<sing key={key} tempo={tempo}{notation_attr}>{lyrics}</sing>'

            return ToolResult(
                success=True,
                data={
                    "action": "sing",
                    "text": sing_text,
                    "lyrics": lyrics,
                    "notation": notation,
                    "key": key,
                    "tempo": tempo,
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=f"生成歌曲失败: {e}")
