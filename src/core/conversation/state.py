# -*- coding: utf-8 -*-
"""
对话状态定义

包含对话状态枚举、配置数据类、性能指标等共享数据结构。
从 conversation_manager.py 拆分而来，作为对话模块的统一数据层。
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """对话状态"""
    IDLE = "idle"                  # 空闲，等待用户说话
    LISTENING = "listening"        # 正在监听用户
    PROCESSING = "processing"      # 正在处理（ASR + Agent）
    SPEAKING = "speaking"          # AI 正在说话
    PAUSED = "paused"             # 暂停


@dataclass
class ConversationConfig:
    """对话配置

    合并了同步/异步对话管理器所需的全部配置字段。
    所有字段都有合理默认值，可按需覆盖。
    """
    # ---- ASR 配置 ----
    asr_model_dir: Optional[str] = None      # ASR 模型目录（本地 FunASR）
    asr_vad_dir: Optional[str] = None        # VAD 模型目录（异步管理器使用）
    asr_provider: str = "funasr"             # "funasr" | "whisper"
    asr_device: str = "auto"                 # "auto" | "cpu" | "cuda" | "cuda:0"
    asr_stream_profile: str = "balanced"     # "low_latency" | "balanced" | "accuracy"
    whisper_api_base: Optional[str] = None   # 远程 Whisper API
    whisper_api_key: Optional[str] = None    # API Key
    use_vad: bool = True                     # 使用 VAD
    use_text_input: bool = False             # 使用终端文字输入（禁用 ASR/麦克风）

    # ---- PUNC 配置（标点恢复）----
    enable_punc: bool = True
    punc_model_id: Optional[str] = None
    punc_device: str = "auto"

    # ---- TTS 配置 ----
    tts_mode: str = "remote"                 # "local" | "remote"（异步管理器使用）
    tts_model_dir: Optional[str] = None      # TTS 模型目录（本地模式）
    tts_remote_url: str = "http://localhost:5001"  # TTS 服务地址（远程模式）
    tts_spk_id: str = "玲"                   # 说话人 ID

    # ---- Agent 配置 ----
    user_id: str = "default_user"

    # ---- 音频 / VAD 配置 ----
    sample_rate: int = 16000
    silence_threshold: float = 0.01
    silence_duration: float = 0.6            # 静音多久认为说完
    vad_backend: str = "rms"                 # "rms" | "silero"
    vad_preset: str = "balanced"             # "aggressive" | "balanced" | "conservative"
    vad_threshold: float = 0.5               # 异步管理器使用的 VAD 阈值

    # ---- 交互配置 ----
    interrupt_on_speak: bool = True
    auto_listen: bool = True

    # ---- SER 配置（语音情绪识别）----
    enable_ser: bool = True
    ser_model_id: Optional[str] = None
    ser_device: str = "auto"
    ser_min_audio_sec: float = 0.8

    # ---- SV 配置（说话人验证门控）----
    enable_sv: bool = False
    sv_model_id: Optional[str] = None
    sv_device: str = "auto"
    sv_threshold: float = 0.38
    sv_min_audio_sec: float = 0.8
    sv_enroll_audio: Optional[str] = None    # 参考说话人音频路径
    sv_reject_policy: str = "drop"           # "drop" | "pass"

    # ---- 多说话人识别配置（Speaker Diarization）----
    enable_diarization: bool = False
    diarization_threshold: float = 0.75
    diarization_model_id: Optional[str] = None
    diarization_device: str = "auto"
    diarization_min_audio_sec: float = 0.8
    diarization_storage_path: Optional[str] = None
    diarization_max_speakers: int = 10
    diarization_timeout_ms: int = 500
    notify_speaker_change: bool = True
    allow_concurrent_speakers: bool = False
    voiceprint_cleanup_days: int = 180

    # ---- 流式打断配置（Barge-in / Interrupt）----
    enable_barge_in: bool = True
    interrupt_vad_threshold: float = 0.5
    interrupt_min_speech_ms: int = 300
    interrupt_response_time_ms: int = 200
    interrupt_context_mode: str = "reset"    # "reset" | "continue"
    interrupt_feedback_enabled: bool = True
    interrupt_sound_enabled: bool = False


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
