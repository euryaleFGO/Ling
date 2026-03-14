# -*- coding: utf-8 -*-
"""
表情测试工具
自动检测运行模式:
  - 主项目已运行 → 作为客户端连入已有的 WebSocket 服务器
  - 主项目未运行 → 自己启动 WebSocket 服务器 + 手动启动 Java 前端

使用方法:
  python scripts/test_expressions.py
"""

import asyncio
import json
import socket
import sys
import threading
import math
import time

try:
    import websockets
except ImportError:
    print("请先安装 websockets: pip install websockets")
    sys.exit(1)

HOST = "localhost"
PORT = 8765
WS_URL = f"ws://{HOST}:{PORT}"

# 所有可用表情
EMOTIONS = [
    ("neutral",  "😐 中性/默认"),
    ("joy",      "😊 高兴"),
    ("shy",      "😳 害羞/脸红"),
    ("anger",    "😠 生气"),
    ("sadness",  "😢 悲伤"),
    ("cry",      "😭 哭泣"),
    ("fear",     "😨 害怕"),
    ("surprise", "😲 惊讶"),
    ("think",    "🤔 思考"),
]


def is_port_in_use(port: int) -> bool:
    """检查端口是否已被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, port)) == 0


# ══════════════════════════════════════════════════════
#  模式 A: 客户端模式（主项目已在跑）
# ══════════════════════════════════════════════════════

_ws_client = None
_client_loop = None
_client_ok = False


async def _connect_client():
    global _ws_client, _client_loop, _client_ok
    _client_loop = asyncio.get_running_loop()
    try:
        _ws_client = await websockets.connect(WS_URL)
        _client_ok = True
        print(f"  已连接到主项目的 WebSocket 服务器: {WS_URL}")
        # 保持连接
        await asyncio.Future()
    except Exception as e:
        print(f"  连接失败: {e}")
        _client_ok = False


def _run_client():
    asyncio.run(_connect_client())


async def _client_send(data: str):
    if _ws_client:
        await _ws_client.send(data)


# ══════════════════════════════════════════════════════
#  模式 B: 服务器模式（主项目没在跑）
# ══════════════════════════════════════════════════════

_server_clients = set()
_server_loop = None
_server_ok = False


async def _server_handler(websocket):
    _server_clients.add(websocket)
    addr = websocket.remote_address
    print(f"\n  [WS] Java 前端已连接: {addr}")
    try:
        async for _ in websocket:
            pass
    finally:
        _server_clients.discard(websocket)
        print(f"  [WS] 连接断开: {addr}")


async def _server_broadcast(data: str):
    if not _server_clients:
        return
    await asyncio.gather(*[c.send(data) for c in _server_clients], return_exceptions=True)


async def _start_server():
    global _server_loop, _server_ok
    _server_loop = asyncio.get_running_loop()
    try:
        await websockets.serve(_server_handler, HOST, PORT)
        _server_ok = True
        print(f"  WebSocket 服务器已启动: {WS_URL}")
        print(f"  请手动启动 Java Live2D 前端：")
        print(f"    cd src/frontend/live2d && mvn -q compile exec:java\n")
        await asyncio.Future()
    except OSError:
        print(f"  ⚠ 端口 {PORT} 启动失败")
        _server_ok = False


def _run_server():
    asyncio.run(_start_server())


# ══════════════════════════════════════════════════════
#  统一发送接口
# ══════════════════════════════════════════════════════

_mode = None  # "client" or "server"


def send(msg_dict: dict):
    data = json.dumps(msg_dict, ensure_ascii=False)
    try:
        if _mode == "client":
            if _client_loop and _client_ok:
                asyncio.run_coroutine_threadsafe(_client_send(data), _client_loop)
        elif _mode == "server":
            if _server_loop and _server_ok:
                asyncio.run_coroutine_threadsafe(_server_broadcast(data), _server_loop)
    except RuntimeError:
        print("  ⚠ 发送失败")


def send_emotion(emotion: str):
    send({"type": "emotion", "emotion": emotion})
    print(f"  → 已发送: {emotion}")


def send_subtitle(text: str, emotion: str):
    send({"type": "subtitle", "text": text, "emotion": emotion, "is_final": True})


def send_rms(rms: float):
    send({"type": "audio_rms", "rms": rms})


def print_menu():
    if _mode == "client":
        status = "✅ 客户端已连接到主项目"
    elif _server_ok:
        n = len(_server_clients)
        status = f"✅ {n} 个客户端已连接" if n > 0 else "⏳ 等待 Java 前端连接..."
    else:
        status = "⚠ 未就绪"
    print("\n" + "=" * 50)
    print(f"  Live2D 表情测试工具  [{status}]")
    print("=" * 50)
    for i, (key, label) in enumerate(EMOTIONS):
        print(f"  {i + 1}. {label}  ({key})")
    print("-" * 50)
    print("  m. 测试嘴型（发送 RMS 脉冲）")
    print("  a. 自动轮播所有表情（每个 3 秒）")
    print("  0 / q. 退出")
    print("=" * 50)


def test_mouth():
    """发送一段 RMS 脉冲模拟说话"""
    print("  → 模拟说话 3 秒...")
    for i in range(60):  # 3秒, 每50ms一帧
        t = i / 20.0
        rms = 0.15 + 0.1 * math.sin(t * 8) + 0.05 * math.sin(t * 13)
        send_rms(rms)
        time.sleep(0.05)
    send_rms(0.0)
    print("  → 嘴型测试完成")


def auto_cycle():
    """自动轮播所有表情"""
    print("\n  自动轮播开始（每个表情 3 秒）...")
    for key, label in EMOTIONS:
        print(f"\n  ▶ {label}")
        send_emotion(key)
        send_subtitle(f"当前表情: {label}", key)
        time.sleep(3.0)
    send_emotion("neutral")
    send_subtitle("轮播结束", "neutral")
    print("\n  轮播完成，已恢复中性表情")


def main():
    global _mode

    if is_port_in_use(PORT):
        # 主项目已在运行，以客户端模式连接
        _mode = "client"
        print(f"\n检测到端口 {PORT} 已被占用（主项目正在运行）")
        print("模式: 客户端 → 通过已有 WebSocket 服务器中转指令\n")
        t = threading.Thread(target=_run_client, daemon=True)
        t.start()
        time.sleep(1.0)
        if not _client_ok:
            print("无法连接到主项目 WebSocket 服务器，退出。")
            return
    else:
        # 端口空闲，独立启动服务器
        _mode = "server"
        print(f"\n端口 {PORT} 空闲")
        print("模式: 独立服务器 → 请手动启动 Java 前端连接\n")
        t = threading.Thread(target=_run_server, daemon=True)
        t.start()
        time.sleep(0.8)
        if not _server_ok:
            print("服务器启动失败，退出。")
            return

    try:
        while True:
            print_menu()
            choice = input("\n请输入编号: ").strip().lower()

            if choice in ("0", "q"):
                send_emotion("neutral")
                print("已恢复中性表情，退出。")
                break
            elif choice == "m":
                test_mouth()
            elif choice == "a":
                auto_cycle()
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(EMOTIONS):
                    key, label = EMOTIONS[idx]
                    send_emotion(key)
                    send_subtitle(f"测试表情: {label}", key)
                else:
                    print("  ⚠ 无效编号")
            else:
                print("  ⚠ 无效输入")
    except KeyboardInterrupt:
        send_emotion("neutral")
        print("\n已退出")


if __name__ == "__main__":
    main()
