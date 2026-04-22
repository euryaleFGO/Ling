#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
向 Live2D 前端的 WebSocket(8765) 发送字幕测试消息。

用脚本避免 PowerShell 引号/编码导致的乱码。
"""

import argparse
import asyncio
import json

import websockets


async def _send_payload(payload: dict) -> None:
    async with websockets.connect("ws://localhost:8765") as ws:
        await ws.send(json.dumps(payload, ensure_ascii=False))
        await asyncio.sleep(0.2)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--text", help="字幕文本；支持 \\n 或 \\\\n 表示换行")
    p.add_argument("--emotion", default="neutral", help="subtitle 情绪标签")
    p.add_argument("--motion-group", help="触发动作组名（例如 Bye / Idle / Tap@Body）")
    p.add_argument("--motion-index", type=int, default=0, help="动作组内索引（默认 0）")
    args = p.parse_args()

    if args.motion_group:
        payload = {"type": "motion", "group": args.motion_group, "index": args.motion_index}
        asyncio.run(_send_payload(payload))
        return

    if not args.text:
        raise SystemExit("需要提供 --text（发送字幕）或 --motion-group（触发动作）")

    # 允许命令行用 \n 表示换行（避免在 PowerShell 里直接输入真实换行的麻烦）
    # PowerShell 双引号里常见输入是 \\n（会变成字面量两个反斜杠 + n），这里两种都兼容。
    text = args.text.replace("\\\\n", "\n").replace("\\n", "\n")
    payload = {"type": "subtitle", "text": text, "emotion": args.emotion, "is_final": True}
    asyncio.run(_send_payload(payload))


if __name__ == "__main__":
    main()

