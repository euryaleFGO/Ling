"""
免费基础 TTS：edge-tts（不需要 API Key）

注意：
- edge-tts 实际会调用微软在线语音服务（无需注册 key），属于“云端免费 TTS”。
- 输出默认是 mp3/ogg 等格式；本项目用 mp3，播放依赖 pygame（推荐）或你自行扩展播放器。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EdgeTTSConfig:
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "+0%"
    volume: str = "+0%"


class EdgeTTSEngine:
    def __init__(self, config: EdgeTTSConfig | None = None):
        self.config = config or EdgeTTSConfig()

    async def _synthesize_async(self, text: str, out_file: Path):
        import edge_tts  # runtime import
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.config.voice,
            rate=self.config.rate,
            volume=self.config.volume,
        )
        await communicate.save(str(out_file))

    def text_to_mp3_file(self, text: str, out_file: str | Path) -> Path:
        text = (text or "").strip()
        if not text:
            raise ValueError("text 不能为空")
        out_path = Path(out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(self._synthesize_async(text, out_path))
        return out_path

