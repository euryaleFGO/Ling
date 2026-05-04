# -*- coding: utf-8 -*-
"""
对话状态定义

包含对话状态枚举、配置数据类等共享数据结构
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class ConversationState(Enum):
    """对话状态"""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    PAUSED = "paused"


@dataclass
class ConversationConfig:
    """对话配置"""
    # ASR 配置
    asr_model_dir: Optional[str] = None
    asr_vad_dir: Optional[str] = None
    asr_device: str = "auto"
    asr_stream_profile: str = "balanced"

    # TTS 配置
    tts_mode: str = "remote"  # local, remote, edge
    tts_remote_url: str = "http://localhost:5001"
    tts_spk_id: str = "玲"
    tts_model_dir: Optional[str] = None

    # 音频配置
    sample_rate: int = 16000
    use_text_input: bool = False

    # 用户配置
    user_id: str = "default_user"

    # 打断配置
    enable_barge_in: bool = True
    vad_threshold: float = 0.5

    # 情绪识别
    enable_ser: bool = True
    ser_device: str = "auto"

    # 说话人验证
    enable_sv: bool = False

    # 标点恢复
    enable_punc: bool = True


@dataclass
class TurnMetrics:
    """Turn 性能指标"""
    turn_id: str = ""
    user_text: str = ""
    ai_text: str = ""
    llm_first_token_ms: float = 0.0
    llm_total_ms: float = 0.0
    tts_first_chunk_ms: float = 0.0
    total_latency_ms: float = 0.0
    interrupted: bool = False
