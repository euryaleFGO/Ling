# -*- coding: utf-8 -*-
"""
ASR 引擎 - 基于 FunASR AutoModel 的语音识别接口
支持流式（streaming）和离线识别，使用 PyTorch (.pt) 模型

依赖：pip install funasr torch torchaudio
"""

import os
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Union, Optional, Callable
import numpy as np

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False


@dataclass
class ASRConfig:
    """ASR 配置"""
    # 模型路径（可以是 ModelScope 模型名 或 本地目录路径）
    model_dir: str = None          # Paraformer 流式模型（如 "paraformer-zh-streaming" 或本地路径）
    vad_model: str = None          # VAD 模型名/路径（如 "fsmn-vad" 或本地路径）

    # 推理设置
    device: str = "cpu"            # "cpu" / "cuda:0" 等
    disable_update: bool = True    # 禁止自动下载/更新模型

    # 流式设置
    chunk_size: List[int] = field(default_factory=lambda: [0, 10, 5])
    encoder_chunk_look_back: int = 4
    decoder_chunk_look_back: int = 1
    sample_rate: int = 16000

    # VAD 设置
    use_vad: bool = True
    max_end_sil: int = 800         # 最大结尾静音时长 (ms)


class ASREngine:
    """
    ASR 引擎 - 基于 FunASR AutoModel

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
        asr.start_stream()
        for chunk in audio_chunks:
            text = asr.feed_audio(chunk)
            if text:
                print(text, end="", flush=True)
        final_text = asr.end_stream()
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
        vad_model: Union[str, Path] = None,
        config: ASRConfig = None,
        **kwargs
    ):
        """
        初始化 ASR 引擎

        Args:
            model_dir: Paraformer 模型目录或 ModelScope 模型名
            vad_model: VAD 模型目录或 ModelScope 模型名
            config: ASR 配置对象
            **kwargs: 其他配置参数（会覆盖 config 中的值）
        """
        if config is None:
            config = ASRConfig()

        if model_dir:
            config.model_dir = str(model_dir)
        if vad_model:
            config.vad_model = str(vad_model)

        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)

        self.config = config

        # 自动查找本地模型目录
        if not config.model_dir:
            config.model_dir = self._find_model_dir("paraformer-zh-streaming")
        if not config.vad_model and config.use_vad:
            config.vad_model = self._find_model_dir("fsmn-vad")

        # FunASR AutoModel 实例
        self._model = None           # 流式模型（不含 VAD）
        self._model_offline = None   # 离线模型（含 VAD，按需加载）
        self._stream_cache = {}

        # 麦克风相关
        self._mic_stream = None
        self._mic_running = False
        self._mic_callback = None

        # 延迟加载
        self._model_loaded = False

    # ------------------------------------------------------------------
    #  内部工具
    # ------------------------------------------------------------------

    def _find_model_dir(self, model_name: str) -> Optional[str]:
        """自动查找本地模型目录"""
        search_paths = [
            Path(__file__).parent.parent.parent.parent / "models" / "ASR" / model_name,
            Path.home() / ".cache" / "modelscope" / "hub" / "models" / "iic" / model_name,
            Path.home() / ".cache" / "funasr" / model_name,
        ]
        for path in search_paths:
            if path.exists():
                return str(path)
        # 如果本地找不到，返回 ModelScope 模型名让 AutoModel 自动下载
        return model_name

    def _load_models(self):
        """延迟加载流式模型（不含 VAD，VAD 由外部 record_until_silence 处理）"""
        if self._model_loaded:
            return

        if not self.config.model_dir:
            raise ValueError(
                "未指定模型目录。请设置 model_dir 参数或下载模型到 models/ASR/paraformer-zh-streaming/"
            )

        try:
            from funasr import AutoModel
        except ImportError:
            raise ImportError(
                "请安装 funasr: pip install funasr\n"
                "同时需要 torch 和 torchaudio: pip install torch torchaudio"
            )

        print(f"[ASR] 加载模型: {self.config.model_dir}")

        # 流式模型：不加载 VAD（VAD + streaming 在 FunASR 中不兼容）
        self._model = AutoModel(
            model=self.config.model_dir,
            device=self.config.device,
            disable_update=self.config.disable_update,
        )
        self._model_loaded = True
        print("[ASR] 模型加载完成")

    def _load_offline_model(self):
        """按需加载离线模型（含 VAD，用于整段音频识别）"""
        if self._model_offline is not None:
            return

        from funasr import AutoModel

        kwargs = {
            "model": self.config.model_dir,
            "device": self.config.device,
            "disable_update": self.config.disable_update,
        }
        if self.config.use_vad and self.config.vad_model:
            print(f"[ASR] VAD 模型: {self.config.vad_model}")
            kwargs["vad_model"] = self.config.vad_model
            kwargs["vad_kwargs"] = {"max_single_segment_time": 60000}

        self._model_offline = AutoModel(**kwargs)
        print("[ASR] 离线模型加载完成")

    # ------------------------------------------------------------------
    #  离线识别
    # ------------------------------------------------------------------

    def recognize_file(self, audio_path: Union[str, Path]) -> str:
        """
        识别整个音频文件（非流式，使用含 VAD 的离线模型）
        """
        self._load_models()
        self._load_offline_model()

        res = self._model_offline.generate(
            input=str(audio_path),
            cache={},
            batch_size_s=300,
        )

        if res and len(res) > 0 and "text" in res[0]:
            return res[0]["text"]
        return ""

    def recognize_audio(self, audio: np.ndarray, sample_rate: int = None) -> str:
        """
        识别音频数据（非流式，使用含 VAD 的离线模型）
        """
        self._load_models()
        self._load_offline_model()

        # 确保归一化到 float32 [-1, 1]
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        
        max_val = np.max(np.abs(audio))
        if max_val > 2.0:
            audio = audio / 32768.0

        # 重采样（如需要）
        if sample_rate and sample_rate != self.config.sample_rate:
            try:
                import librosa
                audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=self.config.sample_rate)
            except ImportError:
                raise ImportError("重采样需要 librosa: pip install librosa")

        res = self._model_offline.generate(
            input=audio,
            cache={},
        )

        if res and len(res) > 0 and "text" in res[0]:
            return res[0]["text"]
        return ""

    # ------------------------------------------------------------------
    #  流式识别
    # ------------------------------------------------------------------

    def get_chunk_stride(self) -> int:
        """
        返回流式识别所需的每个 chunk 的样本数。
        对应 Paraformer 流式模型: chunk_size[1] * 960
        外部录制麦克风时应使用此值作为 blocksize。
        """
        return self.config.chunk_size[1] * 960

    def start_stream(self):
        """开始流式识别（重置缓存）"""
        self._load_models()
        self._stream_cache = {}

    def feed_audio(self, audio_chunk: np.ndarray) -> str:
        """
        输入音频块进行流式识别

        Args:
            audio_chunk: 音频数据块 (float32 [-1,1] 或 int16, 16kHz, 单声道)

        Returns:
            当前识别结果（如果有）
        """
        if not self._model_loaded:
            self._load_models()

        # 确保数据为 float32 且在 [-1, 1] 范围
        if audio_chunk.dtype == np.int16:
            audio_chunk = audio_chunk.astype(np.float32) / 32768.0
        elif audio_chunk.dtype != np.float32:
            audio_chunk = audio_chunk.astype(np.float32)
        
        # 检查值域，如果偶然收到未归一化的 float32 数据
        max_val = np.max(np.abs(audio_chunk))
        if max_val > 2.0:
            audio_chunk = audio_chunk / 32768.0

        res = self._model.generate(
            input=audio_chunk,
            cache=self._stream_cache,
            is_final=False,
            chunk_size=self.config.chunk_size,
            encoder_chunk_look_back=self.config.encoder_chunk_look_back,
            decoder_chunk_look_back=self.config.decoder_chunk_look_back,
        )

        if res and len(res) > 0 and "text" in res[0]:
            return res[0]["text"]
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
        else:
            # 确保归一化
            if audio_chunk.dtype == np.int16:
                audio_chunk = audio_chunk.astype(np.float32) / 32768.0
            elif audio_chunk.dtype != np.float32:
                audio_chunk = audio_chunk.astype(np.float32)
            max_val = np.max(np.abs(audio_chunk))
            if max_val > 2.0:
                audio_chunk = audio_chunk / 32768.0

        res = self._model.generate(
            input=audio_chunk,
            cache=self._stream_cache,
            is_final=True,
            chunk_size=self.config.chunk_size,
            encoder_chunk_look_back=self.config.encoder_chunk_look_back,
            decoder_chunk_look_back=self.config.decoder_chunk_look_back,
        )

        self._stream_cache = {}

        if res and len(res) > 0 and "text" in res[0]:
            return res[0]["text"]
        return ""

    # ------------------------------------------------------------------
    #  麦克风实时识别
    # ------------------------------------------------------------------

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

        chunk_stride = self.config.chunk_size[1] * 960  # chunk_size[1] * 60ms * 16samples/ms

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
            blocksize=chunk_stride,
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

    # ------------------------------------------------------------------
    #  状态查询
    # ------------------------------------------------------------------

    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._model_loaded

    def get_config(self) -> ASRConfig:
        """获取配置"""
        return self.config
