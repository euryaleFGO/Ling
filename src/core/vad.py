# -*- coding: utf-8 -*-
"""
语音活动检测 (VAD) 模块
支持 RMS 能量法和 Silero 神经网络两种后端

VAD 负责判断「当前音频块是否有语音」，Endpoint 逻辑（何时结束录音）在 audio_io 中。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np

try:
    from core.log import log
except ImportError:
    class _Fallback:
        @staticmethod
        def debug(msg): pass
        @staticmethod
        def info(msg): print(msg)
        @staticmethod
        def warn(msg): print(msg)
        @staticmethod
        def error(msg): print(msg)
    log = _Fallback()


# ---------------------------------------------------------------------------
#  VADConfig：统一参数化
# ---------------------------------------------------------------------------

@dataclass
class VADConfig:
    """
    VAD / Endpoint 参数
    
    preset 可选: "aggressive" | "balanced" | "conservative"
    - aggressive: 低延迟，快速结束，可能截断尾音
    - balanced: 折中
    - conservative: 更稳妥，减少截断，延迟略高
    """
    # 后端: "rms" 或 "silero"
    backend: Literal["rms", "silero"] = "rms"
    
    # 静音持续多久认为说完（秒）
    silence_duration: float = 0.6
    
    # 最少连续 N 个语音块才认为「真正开始说话」（防误触发）
    min_speech_chunks: int = 1
    
    # 语音结束后再多录 N 个块（防止截断尾音）
    hangover_chunks: int = 1
    
    # 预缓冲块数（语音开始时回溯，防止开头吃字）
    pre_buffer_chunks: int = 2
    
    # RMS 专用
    silence_threshold: float = 0.008
    noise_floor_alpha: float = 0.05
    
    # Silero 专用
    silero_threshold: float = 0.5  # 语音概率阈值
    
    @classmethod
    def preset(cls, name: Literal["aggressive", "balanced", "conservative"]) -> "VADConfig":
        """预设配置"""
        presets = {
            "aggressive": cls(
                silence_duration=0.4,
                min_speech_chunks=1,
                hangover_chunks=1,
                pre_buffer_chunks=1,
            ),
            "balanced": cls(
                silence_duration=0.6,
                min_speech_chunks=1,
                hangover_chunks=1,
                pre_buffer_chunks=2,
            ),
            "conservative": cls(
                silence_duration=0.9,
                min_speech_chunks=2,
                hangover_chunks=2,
                pre_buffer_chunks=3,
            ),
        }
        return presets[name]


# ---------------------------------------------------------------------------
#  VAD 后端
# ---------------------------------------------------------------------------

class VADBackend:
    """VAD 后端基类"""
    
    def detect_speech(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> bool:
        """
        检测当前音频块是否有语音
        
        Args:
            audio_chunk: float32 [-1,1] 或 int16
            sample_rate: 采样率
            
        Returns:
            True 表示有语音
        """
        raise NotImplementedError
    
    def reset(self):
        """重置内部状态（如噪声校准）"""
        pass


class RMSVADBackend(VADBackend):
    """RMS 能量 + 自适应噪声底噪"""
    
    def __init__(self, config: VADConfig):
        self.config = config
        self._noise_floor = 0.0
        self._noise_floor_initialized = False
        self._calibration_chunks = 0
    
    def _compute_rms(self, audio: np.ndarray) -> float:
        if audio.dtype == np.int16:
            a = audio.astype(np.float32) / 32768.0
        else:
            a = audio.astype(np.float32)
        return float(np.sqrt(np.mean(a ** 2)))
    
    def _update_noise_floor(self, rms: float):
        alpha = self.config.noise_floor_alpha
        if not self._noise_floor_initialized:
            self._calibration_chunks += 1
            if self._calibration_chunks == 1:
                self._noise_floor = rms
            else:
                if rms < self._noise_floor * 4.0:
                    self._noise_floor = self._noise_floor * 0.7 + rms * 0.3
            if self._calibration_chunks >= 5:
                self._noise_floor_initialized = True
                log.debug(f"[VAD/RMS] 噪声底噪校准完成: {self._noise_floor:.5f}")
        else:
            if rms < self._noise_floor * 2.0:
                self._noise_floor = self._noise_floor * (1 - alpha) + rms * alpha
    
    def detect_speech(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> bool:
        rms = self._compute_rms(audio_chunk)
        self._update_noise_floor(rms)
        th = max(self.config.silence_threshold, self._noise_floor * 2.5)
        return rms > th
    
    def reset(self):
        self._noise_floor = 0.0
        self._noise_floor_initialized = False
        self._calibration_chunks = 0


class SileroVADBackend(VADBackend):
    """
    Silero VAD - 神经网络语音活动检测
    
    优势：准确率高、抗噪强、对 150-250ms 停顿检测更好
    依赖: pip install silero-vad
    建议 chunk >= 32ms (512 samples @ 16kHz)，当前实现接受任意长度
    """
    
    def __init__(self, config: VADConfig):
        self.config = config
        self._model = None
        self._sample_rate = 16000
    
    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from silero_vad import load_silero_vad
            self._model = load_silero_vad()
            log.debug("[VAD/Silero] 模型加载完成")
        except ImportError:
            raise ImportError(
                "Silero VAD 需要安装: pip install silero-vad\n"
                "或切换为 RMS 后端: vad_backend='rms'"
            )
    
    def detect_speech(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> bool:
        self._ensure_model()
        self._sample_rate = sample_rate
        
        if audio_chunk.dtype == np.int16:
            audio = audio_chunk.astype(np.float32) / 32768.0
        else:
            audio = audio_chunk.astype(np.float32)
        
        import torch
        t = torch.from_numpy(audio).float()
        with torch.no_grad():
            prob = self._model(t, sample_rate)
        # 可能是标量或 1D tensor（每 512 样本一个概率）
        p = float(prob.max() if hasattr(prob, "dim") and prob.dim() > 0 else prob)
        return p > self.config.silero_threshold


def create_vad(config: VADConfig) -> VADBackend:
    """根据配置创建 VAD 后端"""
    if config.backend == "rms":
        return RMSVADBackend(config)
    elif config.backend == "silero":
        return SileroVADBackend(config)
    else:
        raise ValueError(f"未知 VAD 后端: {config.backend}")
