# -*- coding: utf-8 -*-
"""
配置管理器

功能：
1. 加载配置文件
2. 验证配置参数
3. 提供默认值
4. 运行时热更新（可选）
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

from core.log import log


@dataclass
class ASRConfig:
    """ASR 配置"""
    provider: str = "funasr"
    device: str = "auto"
    stream_profile: str = "balanced"
    hotwords: list = field(default_factory=list)
    hotword_weight: float = 10.0
    enable_model_cache: bool = True
    cache_warmup: bool = False


@dataclass
class TTSConfig:
    """TTS 配置"""
    enable_cache: bool = True
    cache_size: int = 100
    cache_common_phrases: list = field(default_factory=lambda: [
        "好的", "明白了", "收到", "没问题", "我知道了"
    ])
    parallel_synthesis: bool = True
    max_workers: int = 2


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


@dataclass
class SystemConfig:
    """系统配置（根配置）"""
    version: str = "1.0.0"
    description: str = "流式打断与性能优化配置"
    asr: ASRConfig = field(default_factory=ASRConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    interrupt: InterruptConfig = field(default_factory=InterruptConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    speaker_recognition: SpeakerRecognitionConfig = field(default_factory=SpeakerRecognitionConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)
    general: GeneralConfig = field(default_factory=GeneralConfig)


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认为 config/interrupt_config.json
        """
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "interrupt_config.json"
        
        self.config_path = Path(config_path)
        self.config: SystemConfig = SystemConfig()
        self._file_mtime: Optional[float] = None
    
    def load(self) -> SystemConfig:
        """
        加载配置文件
        
        Returns:
            SystemConfig: 系统配置对象
        """
        if not self.config_path.exists():
            log.warn(f"配置文件不存在: {self.config_path}，使用默认配置")
            return self.config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 更新文件修改时间
            self._file_mtime = self.config_path.stat().st_mtime
            
            # 解析配置
            self.config = self._parse_config(data)
            
            # 验证配置
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
    
    def _parse_config(self, data: Dict[str, Any]) -> SystemConfig:
        """解析配置数据"""
        config = SystemConfig()
        
        # 基本信息
        config.version = data.get("version", "1.0.0")
        config.description = data.get("description", "")
        
        # ASR 配置
        if "asr" in data:
            asr_data = data["asr"]
            config.asr = ASRConfig(
                provider=asr_data.get("provider", "funasr"),
                device=asr_data.get("device", "auto"),
                stream_profile=asr_data.get("stream_profile", "balanced"),
                hotwords=asr_data.get("hotwords", []),
                hotword_weight=asr_data.get("hotword_weight", 10.0),
                enable_model_cache=asr_data.get("enable_model_cache", True),
                cache_warmup=asr_data.get("cache_warmup", False),
            )
        
        # TTS 配置
        if "tts" in data:
            tts_data = data["tts"]
            config.tts = TTSConfig(
                enable_cache=tts_data.get("enable_cache", True),
                cache_size=tts_data.get("cache_size", 100),
                cache_common_phrases=tts_data.get("cache_common_phrases", []),
                parallel_synthesis=tts_data.get("parallel_synthesis", True),
                max_workers=tts_data.get("max_workers", 2),
            )
        
        # 打断配置
        if "interrupt" in data:
            int_data = data["interrupt"]
            config.interrupt = InterruptConfig(
                enable_barge_in=int_data.get("enable_barge_in", True),
                vad_threshold=int_data.get("vad_threshold", 0.5),
                min_speech_ms=int_data.get("min_speech_ms", 300),
                response_time_ms=int_data.get("response_time_ms", 200),
                context_mode=int_data.get("context_mode", "reset"),
                feedback_enabled=int_data.get("feedback_enabled", True),
                sound_enabled=int_data.get("sound_enabled", False),
            )
        
        # 音频配置
        if "audio" in data:
            audio_data = data["audio"]
            config.audio = AudioConfig(
                sample_rate=audio_data.get("sample_rate", 16000),
                silence_threshold=audio_data.get("silence_threshold", 0.01),
                silence_duration=audio_data.get("silence_duration", 0.6),
                vad_backend=audio_data.get("vad_backend", "rms"),
                vad_preset=audio_data.get("vad_preset", "balanced"),
                use_vad=audio_data.get("use_vad", True),
            )
        
        # 性能监控配置
        if "performance" in data:
            perf_data = data["performance"]
            config.performance = PerformanceConfig(
                enable_monitoring=perf_data.get("enable_monitoring", True),
                max_history_size=perf_data.get("max_history_size", 100),
                export_interval_seconds=perf_data.get("export_interval_seconds", 300),
                export_format=perf_data.get("export_format", "json"),
            )
        
        # 声纹识别配置
        if "speaker_recognition" in data:
            sr_data = data["speaker_recognition"]
            config.speaker_recognition = SpeakerRecognitionConfig(
                enable=sr_data.get("enable", False),
                async_recognition=sr_data.get("async_recognition", True),
                timeout_ms=sr_data.get("timeout_ms", 500),
                enable_cache=sr_data.get("enable_cache", True),
                cache_size=sr_data.get("cache_size", 100),
            )
        
        # 高级配置
        if "advanced" in data:
            adv_data = data["advanced"]
            config.advanced = AdvancedConfig(
                enable_debug_logging=adv_data.get("enable_debug_logging", False),
                log_performance_metrics=adv_data.get("log_performance_metrics", True),
                auto_optimize=adv_data.get("auto_optimize", False),
            )

        # 通用配置
        if "general" in data:
            gen_data = data["general"]
            config.general = GeneralConfig(
                use_text_input=gen_data.get("use_text_input", False),
            )
        
        return config
    
    def _validate_config(self):
        """验证配置参数"""
        errors = []
        
        # 验证 ASR 配置
        if self.config.asr.stream_profile not in ["low_latency", "balanced", "accuracy"]:
            errors.append(f"无效的 ASR stream_profile: {self.config.asr.stream_profile}")
        
        # 验证 TTS 配置
        if self.config.tts.cache_size < 0:
            errors.append(f"无效的 TTS cache_size: {self.config.tts.cache_size}")
        
        if self.config.tts.max_workers < 1:
            errors.append(f"无效的 TTS max_workers: {self.config.tts.max_workers}")
        
        # 验证打断配置
        if self.config.interrupt.context_mode not in ["reset", "continue"]:
            errors.append(f"无效的 interrupt context_mode: {self.config.interrupt.context_mode}")
        
        if self.config.interrupt.min_speech_ms < 0:
            errors.append(f"无效的 interrupt min_speech_ms: {self.config.interrupt.min_speech_ms}")
        
        # 验证音频配置
        if self.config.audio.vad_backend not in ["rms", "silero"]:
            errors.append(f"无效的 audio vad_backend: {self.config.audio.vad_backend}")
        
        if self.config.audio.vad_preset not in ["sensitive", "balanced", "aggressive"]:
            errors.append(f"无效的 audio vad_preset: {self.config.audio.vad_preset}")
        
        # 验证性能监控配置
        if self.config.performance.export_format not in ["json", "csv"]:
            errors.append(f"无效的 performance export_format: {self.config.performance.export_format}")
        
        if errors:
            error_msg = "\n".join(errors)
            log.error(f"配置验证失败:\n{error_msg}")
            raise ValueError(f"配置验证失败:\n{error_msg}")
    
    def save(self, config: Optional[SystemConfig] = None):
        """
        保存配置到文件
        
        Args:
            config: 要保存的配置对象，默认为当前配置
        """
        if config is not None:
            self.config = config
        
        # 转换为字典
        data = {
            "version": self.config.version,
            "description": self.config.description,
            "asr": {
                "provider": self.config.asr.provider,
                "device": self.config.asr.device,
                "stream_profile": self.config.asr.stream_profile,
                "hotwords": self.config.asr.hotwords,
                "hotword_weight": self.config.asr.hotword_weight,
                "enable_model_cache": self.config.asr.enable_model_cache,
                "cache_warmup": self.config.asr.cache_warmup,
            },
            "tts": {
                "enable_cache": self.config.tts.enable_cache,
                "cache_size": self.config.tts.cache_size,
                "cache_common_phrases": self.config.tts.cache_common_phrases,
                "parallel_synthesis": self.config.tts.parallel_synthesis,
                "max_workers": self.config.tts.max_workers,
            },
            "interrupt": {
                "enable_barge_in": self.config.interrupt.enable_barge_in,
                "vad_threshold": self.config.interrupt.vad_threshold,
                "min_speech_ms": self.config.interrupt.min_speech_ms,
                "response_time_ms": self.config.interrupt.response_time_ms,
                "context_mode": self.config.interrupt.context_mode,
                "feedback_enabled": self.config.interrupt.feedback_enabled,
                "sound_enabled": self.config.interrupt.sound_enabled,
            },
            "audio": {
                "sample_rate": self.config.audio.sample_rate,
                "silence_threshold": self.config.audio.silence_threshold,
                "silence_duration": self.config.audio.silence_duration,
                "vad_backend": self.config.audio.vad_backend,
                "vad_preset": self.config.audio.vad_preset,
                "use_vad": self.config.audio.use_vad,
            },
            "performance": {
                "enable_monitoring": self.config.performance.enable_monitoring,
                "max_history_size": self.config.performance.max_history_size,
                "export_interval_seconds": self.config.performance.export_interval_seconds,
                "export_format": self.config.performance.export_format,
            },
            "speaker_recognition": {
                "enable": self.config.speaker_recognition.enable,
                "async_recognition": self.config.speaker_recognition.async_recognition,
                "timeout_ms": self.config.speaker_recognition.timeout_ms,
                "enable_cache": self.config.speaker_recognition.enable_cache,
                "cache_size": self.config.speaker_recognition.cache_size,
            },
            "advanced": {
                "enable_debug_logging": self.config.advanced.enable_debug_logging,
                "log_performance_metrics": self.config.advanced.log_performance_metrics,
                "auto_optimize": self.config.advanced.auto_optimize,
            },
            "general": {
                "use_text_input": self.config.general.use_text_input,
            },
        }
        
        # 确保目录存在
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存到文件
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # 更新文件修改时间
            self._file_mtime = self.config_path.stat().st_mtime
            
            log.info(f"配置文件保存成功: {self.config_path}")
        except Exception as e:
            log.error(f"保存配置文件失败: {e}")
            raise
    
    def check_for_updates(self) -> bool:
        """
        检查配置文件是否已更新
        
        Returns:
            bool: 如果文件已更新返回 True
        """
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
        """
        如果配置文件已更改，则重新加载
        
        Returns:
            bool: 如果重新加载了配置返回 True
        """
        if self.check_for_updates():
            log.info("检测到配置文件更新，正在重新加载...")
            self.load()
            return True
        return False


# 全局配置管理器实例
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
