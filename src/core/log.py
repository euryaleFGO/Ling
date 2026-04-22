# -*- coding: utf-8 -*-
"""
全局日志控制

根据 --debug 标志决定是否输出调试信息。
正常模式下只显示关键信息，保持终端简洁。
支持控制台输出 + 文件输出（写入 src/logs/）。

用法:
    from core.log import log, set_debug

    log.info("始终显示")
    log.debug("仅调试模式显示")
    log.tts("TTS 专用日志")
    log.tts_segment("TTS 段日志")
"""

import os
import sys
import time
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
import logging

# 全局调试模式
_debug_mode: bool = False

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def set_debug(enabled: bool):
    """设置全局调试模式"""
    global _debug_mode
    _debug_mode = enabled
    # 同步到 root logger
    if _debug_mode:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)


def is_debug() -> bool:
    """当前是否处于调试模式"""
    return _debug_mode


# ========== 配置各模块 logger ==========

def _get_logger(name: str, level=logging.DEBUG) -> logging.Logger:
    """获取或创建指定名称的 logger"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    # 文件 handler（保留所有日志，按天轮转）
    date_str = datetime.now().strftime("%Y%m%d")
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, f"{name}_{date_str}.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    file_handler.setFormatter(file_fmt)

    # 控制台 handler（WARNING 及以上才显示）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_fmt = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# 各模块 logger
_logger_general = _get_logger("agent")
_logger_tts = _get_logger("tts")
_logger_tts_segment = _get_logger("tts_segment")
_logger_asr = _get_logger("asr")
_logger_conv = _get_logger("conversation")


class _Logger:
    """极简日志工具，替代散落的 print"""

    @staticmethod
    def info(msg: str):
        """关键信息，始终显示"""
        print(msg)
        _logger_general.info(msg)

    @staticmethod
    def debug(msg: str):
        """调试信息，仅 --debug 时显示"""
        if _debug_mode:
            print(msg)
        _logger_general.debug(msg)

    @staticmethod
    def warn(msg: str):
        """警告，始终显示"""
        print(f"⚠ {msg}")
        _logger_general.warning(msg)

    @staticmethod
    def error(msg: str):
        """错误，始终显示"""
        print(f"✖ {msg}")
        _logger_general.error(msg)

    # ---- TTS 专用日志（全部写入文件）----
    @staticmethod
    def tts(msg: str):
        """TTS 一般日志，写入 tts_*.log"""
        _logger_tts.info(msg)

    @staticmethod
    def tts_debug(msg: str):
        """TTS 调试日志（受 debug 开关控制）"""
        _logger_tts.debug(msg)

    @staticmethod
    def tts_segment(msg: str):
        """TTS 段日志（每个 segment 的收发情况），写入 tts_segment_*.log"""
        _logger_tts_segment.info(msg)

    # ---- ASR 专用日志 ----
    @staticmethod
    def asr(msg: str):
        _logger_asr.info(msg)

    @staticmethod
    def asr_debug(msg: str):
        _logger_asr.debug(msg)

    # ---- Conversation 专用日志 ----
    @staticmethod
    def conv(msg: str):
        _logger_conv.info(msg)

    @staticmethod
    def conv_debug(msg: str):
        _logger_conv.debug(msg)


log = _Logger()
