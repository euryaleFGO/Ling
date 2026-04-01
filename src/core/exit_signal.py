# -*- coding: utf-8 -*-
"""
应用退出信号

用于在 Agent 工具线程与对话主循环之间传递“请求退出程序”的意图。
"""

from __future__ import annotations

import threading
from typing import Optional


_event = threading.Event()
_lock = threading.Lock()
_reason = ""


def request_exit(reason: str = "") -> None:
    """发起退出请求。"""
    global _reason
    with _lock:
        _reason = (reason or "").strip()
        _event.set()


def is_exit_requested() -> bool:
    """是否已请求退出。"""
    return _event.is_set()


def consume_exit_request() -> Optional[str]:
    """消费一次退出请求并清除标记，返回退出原因。"""
    global _reason
    with _lock:
        if not _event.is_set():
            return None
        reason = _reason
        _reason = ""
        _event.clear()
        return reason
