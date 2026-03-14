# -*- coding: utf-8 -*-
"""
ASR 引擎 - 统一的语音识别接口
提供简单易用的 API，支持流式和离线识别
"""

import os
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import List, Union, Optional, Callable
import numpy as np

try:
    import librosa
except ImportError:
    raise ImportError("请安装 librosa: pip install librosa")

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

from .core.paraformer import ParaformerStreaming
from .core.vad import FsmnVAD, FsmnVADOnline


@dataclass
class ASRConfig:
    """ASR 配置"""
    # 模型路径
    model_dir: str = None  # Paraformer 流式模型目录
    vad_dir: str = None    # VAD 模型目录（可选）
    
    # 推理设置
    device_id: str = "-1"  # "-1" 表示 CPU，"0" 表示 GPU 0
    quantize: bool = False  # 是否使用量化模型
    intra_op_num_threads: int = 4  # CPU 推理线程数
    
    # 流式设置
    chunk_size: List[int] = None  # 流式块大小 [左, 中, 右]，默认 [5, 10, 5]
    sample_rate: int = 16000  # 采样率
    
    # VAD 设置
    use_vad: bool = True  # 是否使用 VAD
    max_end_sil: int = 800  # 最大结尾静音时长 (ms)


class ASREngine:
    """
    ASR 引擎 - 统一的语音识别接口
    
    使用示例:
    
    1. 离线识别（识别整个音频文件）:
        ```python
        asr = ASREngine(model_dir="models/ASR/paraformer-zh-streaming")
        text = asr.recognize_file("audio.wav")
        print(text)
        ```
    
    2. 流式识别（实时处理音频流）:
        ```python
        asr = ASREngine(model_dir="models/ASR/paraformer-zh-streaming")
        
        # 开始流式识别
        asr.start_stream()
        
        # 输入音频块
        for chunk in audio_chunks:
            text = asr.feed_audio(chunk)
            if text:
                print(text, end="", flush=True)
        
        # 结束识别
        final_text = asr.end_stream()
        print(final_text)
        ```
    
    3. 麦克风实时识别:
        ```python
        asr = ASREngine(model_dir="models/ASR/paraformer-zh-streaming")
        
        def on_result(text, is_final):
            print(text, end="" if not is_final else "\\n")
        
        asr.start_microphone(callback=on_result)
        # ... 按 Ctrl+C 停止
        asr.stop_microphone()
        ```
    """

    def __init__(
        self,
        model_dir: Union[str, Path] = None,
        vad_dir: Union[str, Path] = None,
        config: ASRConfig = None,
        **kwargs
    ):
        """
        初始化 ASR 引擎
        
        Args:
            model_dir: Paraformer 模型目录
            vad_dir: VAD 模型目录（可选）
            config: ASR 配置对象
            **kwargs: 其他配置参数
        """
        # 处理配置
        if config is None:
            config = ASRConfig()
        
        if model_dir:
            config.model_dir = str(model_dir)
        if vad_dir:
            config.vad_dir = str(vad_dir)
        
        # 更新其他配置
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        self.config = config
        
        # 自动查找模型目录
        if not config.model_dir:
            config.model_dir = self._find_model_dir("paraformer-zh-streaming")
        if not config.vad_dir and config.use_vad:
            config.vad_dir = self._find_model_dir("fsmn-vad")
        
        # 初始化模型
        self._asr_model = None
        self._vad_model = None
        self._stream_cache = {}
        self._vad_cache = {}
        
        # 麦克风相关
        self._mic_stream = None
        self._mic_thread = None
        self._mic_running = False
        self._mic_callback = None
        
        # 延迟加载模型
        self._model_loaded = False

    def _find_model_dir(self, model_name: str) -> Optional[str]:
        """自动查找模型目录"""
        # 尝试常见路径
        search_paths = [
            Path(__file__).parent.parent.parent.parent / "models" / "ASR" / model_name,
            Path.home() / ".cache" / "funasr" / model_name,
            Path("/models/ASR") / model_name,
        ]
        
        for path in search_paths:
            if path.exists():
                return str(path)
        
        return None

    def _load_models(self):
        """延迟加载模型"""
        if self._model_loaded:
            return
        
        if not self.config.model_dir:
            raise ValueError(
                "未指定模型目录。请设置 model_dir 参数或下载模型到 models/ASR/paraformer-zh-streaming/"
            )
        
        # 加载 ASR 模型
        print(f"[ASR] 加载模型: {self.config.model_dir}")
        self._asr_model = ParaformerStreaming(
            model_dir=self.config.model_dir,
            chunk_size=self.config.chunk_size,
            device_id=self.config.device_id,
            quantize=self.config.quantize,
            intra_op_num_threads=self.config.intra_op_num_threads,
        )
        
        # 加载 VAD 模型
        if self.config.use_vad and self.config.vad_dir:
            print(f"[ASR] 加载 VAD 模型: {self.config.vad_dir}")
            self._vad_model = FsmnVADOnline(
                model_dir=self.config.vad_dir,
                device_id=self.config.device_id,
                quantize=self.config.quantize,
                intra_op_num_threads=self.config.intra_op_num_threads,
                max_end_sil=self.config.max_end_sil,
            )
        
        self._model_loaded = True
        print("[ASR] 模型加载完成")

    def recognize_file(self, audio_path: Union[str, Path]) -> str:
        """
        识别音频文件
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            识别结果文本
        """
        self._load_models()
        
        # 加载音频
        audio, sr = librosa.load(str(audio_path), sr=self.config.sample_rate)
        
        # 流式识别
        self.start_stream()
        
        # 按块处理
        chunk_samples = self.config.chunk_size[1] * 960 if self.config.chunk_size else 9600
        results = []
        
        for i in range(0, len(audio), chunk_samples):
            chunk = audio[i:i + chunk_samples]
            is_final = (i + chunk_samples >= len(audio))
            
            if is_final:
                text = self.end_stream(chunk)
            else:
                text = self.feed_audio(chunk)
            
            if text:
                results.append(text)
        
        return "".join(results)

    def recognize_audio(self, audio: np.ndarray, sample_rate: int = None) -> str:
        """
        识别音频数据
        
        Args:
            audio: 音频数据 (numpy 数组)
            sample_rate: 采样率（如果不是 16kHz 会自动重采样）
            
        Returns:
            识别结果文本
        """
        self._load_models()
        
        # 重采样
        if sample_rate and sample_rate != self.config.sample_rate:
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=self.config.sample_rate)
        
        # 确保是 float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        
        # 流式识别
        self.start_stream()
        
        chunk_samples = self.config.chunk_size[1] * 960 if self.config.chunk_size else 9600
        results = []
        
        for i in range(0, len(audio), chunk_samples):
            chunk = audio[i:i + chunk_samples]
            is_final = (i + chunk_samples >= len(audio))
            
            if is_final:
                text = self.end_stream(chunk)
            else:
                text = self.feed_audio(chunk)
            
            if text:
                results.append(text)
        
        return "".join(results)

    def start_stream(self):
        """开始流式识别"""
        self._load_models()
        self._stream_cache = {}
        self._vad_cache = {}
        self._asr_model.reset()

    def feed_audio(self, audio_chunk: np.ndarray) -> str:
        """
        输入音频块进行流式识别
        
        Args:
            audio_chunk: 音频数据块
            
        Returns:
            当前识别结果（如果有）
        """
        if not self._model_loaded:
            self._load_models()
        
        # 确保是 float32
        if audio_chunk.dtype != np.float32:
            audio_chunk = audio_chunk.astype(np.float32)
        
        # 执行识别
        result = self._asr_model(
            audio_chunk,
            param_dict={"cache": self._stream_cache, "is_final": False}
        )
        
        if result and len(result) > 0 and "preds" in result[0]:
            return result[0]["preds"][0]
        return ""

    def end_stream(self, audio_chunk: np.ndarray = None) -> str:
        """
        结束流式识别
        
        Args:
            audio_chunk: 最后一个音频块（可选）
            
        Returns:
            最终识别结果
        """
        if audio_chunk is None:
            audio_chunk = np.zeros(16 * 60, dtype=np.float32)
        elif audio_chunk.dtype != np.float32:
            audio_chunk = audio_chunk.astype(np.float32)
        
        result = self._asr_model(
            audio_chunk,
            param_dict={"cache": self._stream_cache, "is_final": True}
        )
        
        # 重置缓存
        self._stream_cache = {}
        
        if result and len(result) > 0 and "preds" in result[0]:
            return result[0]["preds"][0]
        return ""

    def start_microphone(self, callback: Callable[[str, bool], None] = None):
        """
        开始麦克风实时识别
        
        Args:
            callback: 回调函数，签名为 callback(text: str, is_final: bool)
        """
        if not HAS_SOUNDDEVICE:
            raise ImportError("请安装 sounddevice: pip install sounddevice")
        
        self._load_models()
        self._mic_callback = callback
        self._mic_running = True
        
        self.start_stream()
        
        def audio_callback(indata, frames, time_info, status):
            if status:
                print(f"[ASR] 音频状态: {status}")
            
            audio = indata[:, 0].astype(np.float32)
            text = self.feed_audio(audio)
            
            if text and self._mic_callback:
                self._mic_callback(text, False)
        
        self._mic_stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=1,
            dtype=np.float32,
            blocksize=self.config.chunk_size[1] * 960 if self.config.chunk_size else 9600,
            callback=audio_callback,
        )
        self._mic_stream.start()
        print("[ASR] 麦克风识别已启动")

    def stop_microphone(self) -> str:
        """
        停止麦克风识别
        
        Returns:
            最终识别结果
        """
        self._mic_running = False
        
        if self._mic_stream:
            self._mic_stream.stop()
            self._mic_stream.close()
            self._mic_stream = None
        
        final_text = self.end_stream()
        
        if final_text and self._mic_callback:
            self._mic_callback(final_text, True)
        
        print("[ASR] 麦克风识别已停止")
        return final_text

    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._model_loaded

    def get_config(self) -> ASRConfig:
        """获取配置"""
        return self.config
