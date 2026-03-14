# -*- coding: utf-8 -*-
"""
全局日志控制

根据 --debug 标志决定是否输出调试信息。
正常模式下只显示关键信息，保持终端简洁。

用法:
    from core.log import log, set_debug

    log.info("始终显示")
    log.debug("仅调试模式显示")
"""

_debug_mode: bool = False


def set_debug(enabled: bool):
    """设置全局调试模式"""
    global _debug_mode
    _debug_mode = enabled


def is_debug() -> bool:
    """当前是否处于调试模式"""
    return _debug_mode


class _Logger:
    """极简日志工具，替代散落的 print"""

    @staticmethod
    def info(msg: str):
        """关键信息，始终显示"""
        print(msg)

    @staticmethod
    def debug(msg: str):
        """调试信息，仅 --debug 时显示"""
        if _debug_mode:
            print(msg)

    @staticmethod
    def warn(msg: str):
        """警告，始终显示"""
        print(f"⚠ {msg}")

    @staticmethod
    def error(msg: str):
        """错误，始终显示"""
        print(f"✖ {msg}")


log = _Logger()
