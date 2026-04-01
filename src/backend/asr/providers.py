# -*- coding: utf-8 -*-
"""
ASR 提供商抽象层
支持本地 FunASR 与远程 Whisper API，统一接口便于切换
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union

import numpy as np


class ASRProvider(ABC):
    """
    ASR 提供商抽象基类
    
    本地 FunASR 与远程 Whisper 均可实现此接口：
    - 麦克风始终在本地采集音频
    - 识别可在本地（FunASR）或远程（Whisper API）完成
    - Whisper 仅做 STT（语音转文字），不做 TTS
    """
    
    @property
    def supports_streaming(self) -> bool:
        """是否支持流式识别（实时中间结果）"""
        return False
    
    def get_chunk_stride(self) -> int:
        """
        录音 chunk 大小（样本数）
        流式 ASR 需与模型匹配；Whisper 批次模式可返回任意合理值
        """
        return 5760  # 360ms @ 16kHz，与 Paraformer 兼容
    
    @abstractmethod
    def start_stream(self) -> None:
        """开始流式识别（重置状态）"""
        pass
    
    @abstractmethod
    def feed_audio(self, chunk: np.ndarray) -> str:
        """
        送入音频块
        
        Returns:
            当前识别结果（流式时为增量/累积，批次模式可返回空）
        """
        pass
    
    @abstractmethod
    def end_stream(self, chunk: Optional[np.ndarray] = None) -> str:
        """结束流式识别，返回最终结果"""
        pass
    
    @abstractmethod
    def recognize_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """识别完整音频（批次模式）"""
        pass
    
    def recognize_file(self, path: Union[str, Path]) -> str:
        """识别音频文件"""
        import soundfile as sf
        audio, sr = sf.read(str(path))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return self.recognize_audio(audio, sr)


class FunASRProvider(ASRProvider):
    """本地 FunASR Paraformer 流式识别"""
    
    def __init__(self, model_dir: str = None, vad_model: str = None, device: str = "cpu"):
        from .asr_engine import ASREngine, ASRConfig
        config = ASRConfig(
            model_dir=model_dir,
            vad_model=vad_model,
            device=device,
        )
        self._engine = ASREngine(config=config)
    
    @property
    def supports_streaming(self) -> bool:
        return True
    
    def get_chunk_stride(self) -> int:
        return self._engine.get_chunk_stride()
    
    def start_stream(self) -> None:
        self._engine.start_stream()
    
    def feed_audio(self, chunk: np.ndarray) -> str:
        return self._engine.feed_audio(chunk) or ""
    
    def end_stream(self, chunk: Optional[np.ndarray] = None) -> str:
        return self._engine.end_stream(chunk) or ""
    
    def recognize_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        return self._engine.recognize_audio(audio, sample_rate) or ""


class WhisperRemoteProvider(ASRProvider):
    """
    远程 Whisper API（OpenAI 或兼容接口）
    
    - 仅做 STT，不做 TTS
    - 需本地麦克风采集，录制完成后发送到远程识别
    - 不支持流式，录音结束整段发送
    """
    
    def __init__(
        self,
        api_base: str = "https://api.openai.com/v1",
        api_key: str = None,
        model: str = "whisper-1",
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._buffer: list = []
    
    @property
    def supports_streaming(self) -> bool:
        return False
    
    def get_chunk_stride(self) -> int:
        return 5760  # 与 FunASR 兼容，便于共用录音逻辑
    
    def start_stream(self) -> None:
        self._buffer = []
    
    def feed_audio(self, chunk: np.ndarray) -> str:
        """Whisper 无流式，仅缓冲"""
        self._buffer.append(chunk.copy())
        return ""
    
    def end_stream(self, chunk: Optional[np.ndarray] = None) -> str:
        if chunk is not None:
            self._buffer.append(chunk)
        if not self._buffer:
            return ""
        full = np.concatenate(self._buffer)
        self._buffer = []
        return self.recognize_audio(full, 16000)
    
    def recognize_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        import tempfile
        import wave
        import requests

        if audio.dtype == np.float32:
            audio = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio.tobytes())
            with open(tmp.name, "rb") as rf:
                files = {"file": ("audio.wav", rf, "audio/wav")}
                data = {"model": self.model}
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                try:
                    r = requests.post(
                        f"{self.api_base}/audio/transcriptions",
                        files=files,
                        data=data,
                        headers=headers,
                        timeout=30,
                    )
                except requests.exceptions.Timeout:
                    raise RuntimeError("Whisper API 请求超时（30秒）")
                except requests.exceptions.ConnectionError as e:
                    raise RuntimeError(f"Whisper API 连接失败: {e}")
                except requests.exceptions.RequestException as e:
                    raise RuntimeError(f"Whisper API 请求异常: {e}")
            if r.status_code != 200:
                raise RuntimeError(f"Whisper API 错误: {r.status_code} {r.text}")
            return (r.json().get("text") or "").strip()
        finally:
            Path(tmp.name).unlink(missing_ok=True)
