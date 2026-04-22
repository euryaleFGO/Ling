# -*- coding: utf-8 -*-
"""
WebSocket 消息服务器
Python 后端 → Java Live2D 前端 的实时通信桥梁

替代旧的 HTTP 轮询方案，实现毫秒级推送。

协议格式 (JSON):
  字幕:     {"type": "subtitle",   "text": "...", "emotion": "joy", "is_final": true}
  音频RMS:  {"type": "audio_rms",  "rms": 0.45}
  视觉素:   {"type": "viseme",    "openY": 0.5, "form": 0.3}
  情绪:     {"type": "emotion",    "emotion": "neutral"}
  动作:     {"type": "motion",     "group": "Tap@Body", "index": 0}
  状态:     {"type": "state",      "state": "listening"}
  清除:     {"type": "clear"}

支持的情绪标签:
  neutral, joy, anger, sadness, surprise, shy, think
"""

import asyncio
import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Set

# 确保日志立即输出
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from core.log import log

# ------------------------------------------------------------------
# 尝试导入 websockets；不可用时给出明确提示
# ------------------------------------------------------------------
try:
    import websockets  # type: ignore
    from websockets.server import serve as ws_serve  # websockets >= 10

    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    print("[MessageServer] ⚠ websockets 未安装，请运行: pip install websockets")


# ==================================================================
#  WebSocket 服务器
# ==================================================================
class WebSocketServer:
    """异步 WebSocket 服务器，运行在独立的后台线程中"""

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._ready = threading.Event()

    # ---------- 连接处理 ----------
    async def _handler(self, websocket):
        """处理新的 WebSocket 连接"""
        self.clients.add(websocket)
        addr = websocket.remote_address
        log.debug(f"[MessageServer] 客户端已连接: {addr} (当前 {len(self.clients)} 个)")
        try:
            async for message in websocket:
                # 将客户端发来的消息转发给所有 *其他* 客户端（中继模式）
                # 这使得测试脚本可以作为客户端连入并向 Java 前端发送指令
                for other in self.clients.copy():
                    if other is not websocket:
                        try:
                            await other.send(message)
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            self.clients.discard(websocket)
            log.debug(
                f"[MessageServer] 客户端断开: {addr} (当前 {len(self.clients)} 个)"
            )

    # ---------- 广播 ----------
    async def _broadcast(self, message: str):
        if not self.clients:
            return
        disconnected: Set = set()
        for client in self.clients.copy():
            try:
                await client.send(message)
            except Exception:
                disconnected.add(client)
        self.clients -= disconnected

    # ---------- 线程安全的发送接口 ----------
    def send(self, data: Dict[str, Any]):
        """从任意线程调用，广播 JSON 消息给所有已连接的客户端"""
        if self._loop is None or self._loop.is_closed():
            return
        msg = json.dumps(data, ensure_ascii=False)
        asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)

    # ---------- 生命周期 ----------
    async def _serve(self):
        self._stop_event = asyncio.Event()
        async with ws_serve(self._handler, self.host, self.port):
            log.debug(
                f"[MessageServer] WebSocket 服务已启动: ws://{self.host}:{self.port}"
            )
            self._ready.set()
            await self._stop_event.wait()

    def _run(self):
        """后台线程入口"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            log.error(f"[MessageServer] 服务异常退出: {e}")
        finally:
            self._loop.close()

    def start(self):
        """在后台线程中启动 WebSocket 服务"""
        if not HAS_WEBSOCKETS:
            print("[MessageServer] 无法启动：websockets 未安装")
            return
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="WebSocketServer"
        )
        self._thread.start()
        self._ready.wait(timeout=5)

    def stop(self):
        """停止服务"""
        if self._stop_event and self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread:
            self._thread.join(timeout=3)
        log.debug("[MessageServer] 服务已停止")

    # ---------- 兼容旧 HTTPServer 接口 ----------
    def serve_forever(self):
        """兼容 launcher.py 旧接口（阻塞运行）"""
        self._run()

    def shutdown(self):
        """兼容 launcher.py 旧接口"""
        self.stop()


# ==================================================================
#  模块级单例 & 对外 API
# ==================================================================
_server: Optional[WebSocketServer] = None


def create_server(port: int = 8765, host: str = "localhost") -> WebSocketServer:
    """创建 WebSocket 服务器实例（不启动）"""
    global _server
    _server = WebSocketServer(host=host, port=port)
    return _server


def start_server(port: int = 8765, host: str = "localhost") -> WebSocketServer:
    """创建并立即启动服务器（后台线程）"""
    global _server
    _server = WebSocketServer(host=host, port=port)
    _server.start()
    return _server


# -------------------- 发送消息快捷函数 --------------------

def send_message(text: str, emotion: str = "neutral", is_final: bool = False, **kwargs):
    """
    发送字幕消息到 Live2D 前端

    Args:
        text:     字幕文本
        emotion:  情绪标签 (neutral/joy/anger/sadness/surprise/shy/think)
        is_final: 是否为最终文本（流式完成）
    """
    # 兼容旧接口: send_message(text, is_new=True)
    if "is_new" in kwargs:
        is_final = kwargs["is_new"]
    if _server:
        _server.send(
            {
                "type": "subtitle",
                "text": text,
                "emotion": emotion,
                "is_final": is_final,
            }
        )


def send_audio_rms(rms: float):
    """发送音频 RMS 值（驱动嘴型同步，建议 20-30fps）"""
    if _server:
        _server.send({"type": "audio_rms", "rms": round(rms, 4)})


def send_viseme(openY: float, form: float):
    """发送 viseme 口型数据（由 Rhubarb Lip Sync 生成，替代 RMS）
    
    Args:
        openY: 嘴张开程度 (0.0~1.0，对应 ParamMouthOpenY)
        form:  嘴型形状 (-1.0~1.0，对应 ParamMouthForm，负=圆/悄 正=平/笑)
    """
    if _server:
        _server.send({"type": "viseme", "openY": round(openY, 3), "form": round(form, 3)})


def send_emotion(emotion: str):
    """发送独立的情绪变化"""
    if _server:
        _server.send({"type": "emotion", "emotion": emotion})


def send_motion(group: str, index: int = 0):
    """
    发送动作指令，由 Agent/LLM 情绪自主触发
    模型 hiyori 支持: Idle, Tap, Tap@Body, Flick, FlickDown, Flick@Body
    """
    if _server:
        _server.send({"type": "motion", "group": group, "index": index})


def send_state(state: str):
    """发送对话状态 (idle / listening / processing / speaking)"""
    if _server:
        _server.send({"type": "state", "state": state})


def send_clear():
    """清除 Live2D 气泡框"""
    if _server:
        _server.send({"type": "clear"})


def send_message_stream(text, delay=0.05):
    """兼容旧接口：流式发送消息（逐字符）"""
    for i, char in enumerate(text):
        send_message(text[: i + 1], is_final=(i == len(text) - 1))
        import time
        time.sleep(delay)


# ==================================================================
#  独立运行入口
# ==================================================================
if __name__ == "__main__":
    import os

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

    print("=" * 60)
    print("[MessageServer] 启动信息")
    print("=" * 60)
    print(f"  Python: {sys.executable}")
    print(f"  版本:   {sys.version}")
    print(f"  工作目录: {os.getcwd()}")
    print("=" * 60)
    sys.stdout.flush()

    if not HAS_WEBSOCKETS:
        print("[MessageServer] 错误：请先安装 websockets 库")
        print("  pip install websockets")
        sys.exit(1)

    print(f"[MessageServer] 正在启动 WebSocket 服务 (端口 {port})...")
    sys.stdout.flush()
    start_server(port)

    # 保持主线程存活
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MessageServer] 收到中断信号，正在关闭...")
        if _server:
            _server.stop()
