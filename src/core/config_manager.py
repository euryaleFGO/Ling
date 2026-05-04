# -*- coding: utf-8 -*-
"""
统一配置管理器

功能：
1. 加载配置文件
2. 验证配置参数
3. 提供默认值
4. 运行时热更新（可选）

配置来源优先级：JSON 文件 > 环境变量 > 默认值
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

from core.log import log


# ============================================================
#  子配置 dataclass
# ============================================================

@dataclass
class LLMConfig:
    """LLM 推理配置"""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 120


@dataclass
class ASRConfig:
    """ASR 配置"""
    provider: str = "funasr"
    device: str = "auto"
    stream_profile: str = "balanced"
    model_dir: str = ""
    vad_model_dir: str = ""
    whisper_api_base: str = ""
    whisper_api_key: str = ""
    hotwords: list = field(default_factory=list)
    hotword_weight: float = 10.0
    enable_model_cache: bool = True
    cache_warmup: bool = False


@dataclass
class TTSConfig:
    """TTS 配置"""
    model_dir: str = ""
    remote_url: str = ""
    spk_id: str = "玲"
    enable_cache: bool = True
    cache_size: int = 100
    cache_common_phrases: list = field(default_factory=lambda: [
        "好的", "明白了", "收到", "没问题", "我知道了"
    ])
    parallel_synthesis: bool = True
    max_workers: int = 2


@dataclass
class PuncConfig:
    """标点恢复配置"""
    enable: bool = True
    model_id: str = ""
    device: str = "auto"


@dataclass
class SERConfig:
    """语音情感识别配置"""
    enable: bool = True
    model_id: str = ""
    device: str = "auto"
    min_audio_sec: float = 0.8


@dataclass
class SVConfig:
    """声纹验证配置"""
    enable: bool = False
    model_id: str = ""
    device: str = "auto"
    threshold: float = 0.38
    min_audio_sec: float = 0.8
    enroll_audio: str = ""
    reject_policy: str = "drop"


@dataclass
class DiarizationConfig:
    """多说话人识别配置"""
    enable: bool = False
    threshold: float = 0.75
    model_id: str = ""
    device: str = "auto"
    min_audio_sec: float = 0.8
    storage_path: str = ""
    max_speakers: int = 10
    timeout_ms: int = 500
    notify_speaker_change: bool = True
    allow_concurrent_speakers: bool = False
    voiceprint_cleanup_days: int = 180


@dataclass
class InterruptConfig:
    """打断配置"""
    enable_barge_in: bool = True
    vad_threshold: float = 0.5
    min_speech_ms: int = 300
    response_time_ms: int = 200
    context_mode: str = "reset"
    feedback_enabled: bool = True
    sound_enabled: bool = False


@dataclass
class AudioConfig:
    """音频配置"""
    sample_rate: int = 16000
    silence_threshold: float = 0.01
    silence_duration: float = 0.6
    vad_backend: str = "rms"
    vad_preset: str = "balanced"
    use_vad: bool = True


@dataclass
class PerformanceConfig:
    """性能监控配置"""
    enable_monitoring: bool = True
    max_history_size: int = 100
    export_interval_seconds: int = 300
    export_format: str = "json"


@dataclass
class SpeakerRecognitionConfig:
    """声纹识别配置"""
    enable: bool = False
    async_recognition: bool = True
    timeout_ms: int = 500
    enable_cache: bool = True
    cache_size: int = 100


@dataclass
class AdvancedConfig:
    """高级配置"""
    enable_debug_logging: bool = False
    log_performance_metrics: bool = True
    auto_optimize: bool = False


@dataclass
class GeneralConfig:
    """通用配置"""
    use_text_input: bool = False
    user_id: str = "default_user"
    auto_listen: bool = True


@dataclass
class SystemConfig:
    """系统配置（根配置）"""
    version: str = "2.0.0"
    description: str = "统一系统配置"
    llm: LLMConfig = field(default_factory=LLMConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    punc: PuncConfig = field(default_factory=PuncConfig)
    ser: SERConfig = field(default_factory=SERConfig)
    sv: SVConfig = field(default_factory=SVConfig)
    diarization: DiarizationConfig = field(default_factory=DiarizationConfig)
    interrupt: InterruptConfig = field(default_factory=InterruptConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    speaker_recognition: SpeakerRecognitionConfig = field(default_factory=SpeakerRecognitionConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)
    general: GeneralConfig = field(default_factory=GeneralConfig)


# ============================================================
#  配置解析辅助函数
# ============================================================

def _parse_sub_config(data: dict, cls, prefix: str = ""):
    """从 dict 解析子配置，忽略未知字段"""
    import inspect
    sig = inspect.signature(cls)
    kwargs = {}
    for name, param in sig.parameters.items():
        if name in data:
            kwargs[name] = data[name]
    return cls(**kwargs)


# ============================================================
#  ConfigManager
# ============================================================

class ConfigManager:
    """统一配置管理器"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "settings.json"
            # 兼容旧配置文件名
            if not Path(config_path).exists():
                old_path = project_root / "config" / "interrupt_config.json"
                if old_path.exists():
                    config_path = old_path

        self.config_path = Path(config_path)
        self.config: SystemConfig = SystemConfig()
        self._file_mtime: Optional[float] = None

    def load(self) -> SystemConfig:
        if not self.config_path.exists():
            log.warn(f"配置文件不存在: {self.config_path}，使用默认配置")
            return self.config

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._file_mtime = self.config_path.stat().st_mtime
            self.config = self._parse_config(data)
            self._apply_env_overrides()
            self._validate_config()

            log.info(f"配置文件加载成功: {self.config_path}")
            return self.config

        except json.JSONDecodeError as e:
            log.error(f"配置文件格式错误: {e}")
            log.warn("使用默认配置")
            return self.config
        except Exception as e:
            log.error(f"加载配置文件失败: {e}")
            log.warn("使用默认配置")
            return self.config

    def _apply_env_overrides(self):
        """环境变量覆盖（仅在 JSON 中未设置时生效）"""
        c = self.config

        # LLM
        if not c.llm.api_key:
            c.llm.api_key = os.environ.get("LIYING_LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
        if not c.llm.base_url:
            c.llm.base_url = os.environ.get("LIYING_LLM_BASE_URL") or os.environ.get("BASE_URL") or ""
        if not c.llm.model:
            c.llm.model = os.environ.get("LIYING_LLM_MODEL") or os.environ.get("MODEL") or ""

        # TTS
        if not c.tts.remote_url:
            c.tts.remote_url = os.environ.get("LIYING_TTS_REMOTE_URL") or os.environ.get("REMOTE_TTS_URL") or ""
        if c.tts.spk_id == "玲":  # default value
            env_spk = os.environ.get("LIYING_TTS_SPK_ID")
            if env_spk:
                c.tts.spk_id = env_spk
        if not c.tts.model_dir:
            env_tts_dir = os.environ.get("LIYING_TTS_MODEL_DIR")
            if env_tts_dir:
                c.tts.model_dir = env_tts_dir

        # ASR
        if not c.asr.model_dir:
            env_asr_dir = os.environ.get("LIYING_ASR_MODEL_DIR")
            if env_asr_dir:
                c.asr.model_dir = env_asr_dir
        if not c.asr.vad_model_dir:
            env_vad_dir = os.environ.get("LIYING_ASR_VAD_DIR")
            if env_vad_dir:
                c.asr.vad_model_dir = env_vad_dir

        # General
        if c.general.user_id == "default_user":
            env_uid = os.environ.get("LIYING_USER_ID")
            if env_uid:
                c.general.user_id = env_uid

    def _parse_config(self, data: Dict[str, Any]) -> SystemConfig:
        config = SystemConfig()

        config.version = data.get("version", "2.0.0")
        config.description = data.get("description", "")

        # LLM
        if "llm" in data:
            config.llm = _parse_sub_config(data["llm"], LLMConfig)

        # ASR
        if "asr" in data:
            config.asr = _parse_sub_config(data["asr"], ASRConfig)

        # TTS
        if "tts" in data:
            config.tts = _parse_sub_config(data["tts"], TTSConfig)

        # Punc
        if "punc" in data:
            config.punc = _parse_sub_config(data["punc"], PuncConfig)

        # SER
        if "ser" in data:
            config.ser = _parse_sub_config(data["ser"], SERConfig)

        # SV
        if "sv" in data:
            config.sv = _parse_sub_config(data["sv"], SVConfig)

        # Diarization
        if "diarization" in data:
            config.diarization = _parse_sub_config(data["diarization"], DiarizationConfig)

        # Interrupt
        if "interrupt" in data:
            config.interrupt = _parse_sub_config(data["interrupt"], InterruptConfig)

        # Audio
        if "audio" in data:
            config.audio = _parse_sub_config(data["audio"], AudioConfig)

        # Performance
        if "performance" in data:
            config.performance = _parse_sub_config(data["performance"], PerformanceConfig)

        # Speaker recognition
        if "speaker_recognition" in data:
            config.speaker_recognition = _parse_sub_config(data["speaker_recognition"], SpeakerRecognitionConfig)

        # Advanced
        if "advanced" in data:
            config.advanced = _parse_sub_config(data["advanced"], AdvancedConfig)

        # General
        if "general" in data:
            gen_data = data["general"]
            if "use_text_input" in gen_data:
                config.general.use_text_input = gen_data["use_text_input"]
            if "user_id" in gen_data:
                config.general.user_id = gen_data["user_id"]
            if "auto_listen" in gen_data:
                config.general.auto_listen = gen_data["auto_listen"]

        return config

    def _validate_config(self):
        errors = []

        if self.config.asr.stream_profile not in ["low_latency", "balanced", "accuracy"]:
            errors.append(f"无效的 ASR stream_profile: {self.config.asr.stream_profile}")

        if self.config.tts.cache_size < 0:
            errors.append(f"无效的 TTS cache_size: {self.config.tts.cache_size}")

        if self.config.tts.max_workers < 1:
            errors.append(f"无效的 TTS max_workers: {self.config.tts.max_workers}")

        if self.config.interrupt.context_mode not in ["reset", "continue"]:
            errors.append(f"无效的 interrupt context_mode: {self.config.interrupt.context_mode}")

        if self.config.interrupt.min_speech_ms < 0:
            errors.append(f"无效的 interrupt min_speech_ms: {self.config.interrupt.min_speech_ms}")

        if self.config.audio.vad_backend not in ["rms", "silero"]:
            errors.append(f"无效的 audio vad_backend: {self.config.audio.vad_backend}")

        if self.config.audio.vad_preset not in ["sensitive", "balanced", "aggressive"]:
            errors.append(f"无效的 audio vad_preset: {self.config.audio.vad_preset}")

        if self.config.performance.export_format not in ["json", "csv"]:
            errors.append(f"无效的 performance export_format: {self.config.performance.export_format}")

        if errors:
            error_msg = "\n".join(errors)
            log.error(f"配置验证失败:\n{error_msg}")
            raise ValueError(f"配置验证失败:\n{error_msg}")

    def save(self, config: Optional[SystemConfig] = None):
        if config is not None:
            self.config = config

        c = self.config
        data = {
            "version": c.version,
            "description": c.description,
            "llm": {
                "api_key": c.llm.api_key,
                "base_url": c.llm.base_url,
                "model": c.llm.model,
                "temperature": c.llm.temperature,
                "max_tokens": c.llm.max_tokens,
                "timeout": c.llm.timeout,
            },
            "asr": {
                "provider": c.asr.provider,
                "device": c.asr.device,
                "stream_profile": c.asr.stream_profile,
                "model_dir": c.asr.model_dir,
                "vad_model_dir": c.asr.vad_model_dir,
                "whisper_api_base": c.asr.whisper_api_base,
                "whisper_api_key": c.asr.whisper_api_key,
                "hotwords": c.asr.hotwords,
                "hotword_weight": c.asr.hotword_weight,
                "enable_model_cache": c.asr.enable_model_cache,
                "cache_warmup": c.asr.cache_warmup,
            },
            "tts": {
                "model_dir": c.tts.model_dir,
                "remote_url": c.tts.remote_url,
                "spk_id": c.tts.spk_id,
                "enable_cache": c.tts.enable_cache,
                "cache_size": c.tts.cache_size,
                "cache_common_phrases": c.tts.cache_common_phrases,
                "parallel_synthesis": c.tts.parallel_synthesis,
                "max_workers": c.tts.max_workers,
            },
            "punc": {
                "enable": c.punc.enable,
                "model_id": c.punc.model_id,
                "device": c.punc.device,
            },
            "ser": {
                "enable": c.ser.enable,
                "model_id": c.ser.model_id,
                "device": c.ser.device,
                "min_audio_sec": c.ser.min_audio_sec,
            },
            "sv": {
                "enable": c.sv.enable,
                "model_id": c.sv.model_id,
                "device": c.sv.device,
                "threshold": c.sv.threshold,
                "min_audio_sec": c.sv.min_audio_sec,
                "enroll_audio": c.sv.enroll_audio,
                "reject_policy": c.sv.reject_policy,
            },
            "diarization": {
                "enable": c.diarization.enable,
                "threshold": c.diarization.threshold,
                "model_id": c.diarization.model_id,
                "device": c.diarization.device,
                "min_audio_sec": c.diarization.min_audio_sec,
                "storage_path": c.diarization.storage_path,
                "max_speakers": c.diarization.max_speakers,
                "timeout_ms": c.diarization.timeout_ms,
                "notify_speaker_change": c.diarization.notify_speaker_change,
                "allow_concurrent_speakers": c.diarization.allow_concurrent_speakers,
                "voiceprint_cleanup_days": c.diarization.voiceprint_cleanup_days,
            },
            "interrupt": {
                "enable_barge_in": c.interrupt.enable_barge_in,
                "vad_threshold": c.interrupt.vad_threshold,
                "min_speech_ms": c.interrupt.min_speech_ms,
                "response_time_ms": c.interrupt.response_time_ms,
                "context_mode": c.interrupt.context_mode,
                "feedback_enabled": c.interrupt.feedback_enabled,
                "sound_enabled": c.interrupt.sound_enabled,
            },
            "audio": {
                "sample_rate": c.audio.sample_rate,
                "silence_threshold": c.audio.silence_threshold,
                "silence_duration": c.audio.silence_duration,
                "vad_backend": c.audio.vad_backend,
                "vad_preset": c.audio.vad_preset,
                "use_vad": c.audio.use_vad,
            },
            "performance": {
                "enable_monitoring": c.performance.enable_monitoring,
                "max_history_size": c.performance.max_history_size,
                "export_interval_seconds": c.performance.export_interval_seconds,
                "export_format": c.performance.export_format,
            },
            "speaker_recognition": {
                "enable": c.speaker_recognition.enable,
                "async_recognition": c.speaker_recognition.async_recognition,
                "timeout_ms": c.speaker_recognition.timeout_ms,
                "enable_cache": c.speaker_recognition.enable_cache,
                "cache_size": c.speaker_recognition.cache_size,
            },
            "advanced": {
                "enable_debug_logging": c.advanced.enable_debug_logging,
                "log_performance_metrics": c.advanced.log_performance_metrics,
                "auto_optimize": c.advanced.auto_optimize,
            },
            "general": {
                "use_text_input": c.general.use_text_input,
                "user_id": c.general.user_id,
                "auto_listen": c.general.auto_listen,
            },
        }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self._file_mtime = self.config_path.stat().st_mtime
            log.info(f"配置文件保存成功: {self.config_path}")
        except Exception as e:
            log.error(f"保存配置文件失败: {e}")
            raise

    def check_for_updates(self) -> bool:
        if not self.config_path.exists():
            return False

        try:
            current_mtime = self.config_path.stat().st_mtime
            if self._file_mtime is None or current_mtime > self._file_mtime:
                return True
            return False
        except Exception:
            return False

    def reload_if_changed(self) -> bool:
        if self.check_for_updates():
            log.info("检测到配置文件更新，正在重新加载...")
            self.load()
            return True
        return False


# ============================================================
#  全局单例
# ============================================================

_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager


def load_config() -> SystemConfig:
    """加载配置（便捷函数）"""
    return get_config_manager().config
