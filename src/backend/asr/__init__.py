# -*- coding: utf-8 -*-
"""
ASR (Automatic Speech Recognition) 模块
基于 FunASR AutoModel，支持流式和离线语音识别
使用 PyTorch (.pt) 模型，不再依赖 ONNX Runtime

依赖: pip install funasr torch torchaudio

使用方法:
    from backend.asr import ASREngine

    # 初始化引擎（自动查找本地模型）
    asr = ASREngine(model_dir="models/ASR/paraformer-zh-streaming")

    # 流式识别
    asr.start_stream()
    for audio_chunk in audio_stream:
        text = asr.feed_audio(audio_chunk)
        if text:
            print(text)
    final_text = asr.end_stream()
"""

from .asr_engine import ASREngine, ASRConfig
from .providers import ASRProvider, FunASRProvider, WhisperRemoteProvider

__all__ = [
    "ASREngine",
    "ASRConfig",
    "ASRProvider",
    "FunASRProvider",
    "WhisperRemoteProvider",
]
__version__ = "2.0.0"
