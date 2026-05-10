# -*- coding: utf-8 -*-
"""
ASR 提供商抽象层
支持本地 FunASR 与远程 Whisper API，统一接口便于切换
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union, List

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
    
    def __init__(
        self,
        model_dir: str = None,
        vad_model: str = None,
        device: str = "cpu",
        chunk_size: Optional[List[int]] = None,
        encoder_chunk_look_back: Optional[int] = None,
        decoder_chunk_look_back: Optional[int] = None,
    ):
        from .asr_engine import ASREngine, ASRConfig
        config = ASRConfig(
            model_dir=model_dir,
            vad_model=vad_model,
            device=device,
        )
        if chunk_size:
            config.chunk_size = list(chunk_size)
        if encoder_chunk_look_back is not None:
            config.encoder_chunk_look_back = int(encoder_chunk_look_back)
        if decoder_chunk_look_back is not None:
            config.decoder_chunk_look_back = int(decoder_chunk_look_back)
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
        chunk_size: Optional[List[int]] = None,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._chunk_size = chunk_size or [5, 10, 5]
        self._buffer: list = []

    @property
    def supports_streaming(self) -> bool:
        return False

    def get_chunk_stride(self) -> int:
        return self._chunk_size[1] * 960  # 与本地 FunASR 统一：10*960=9600 (600ms)
    
    def start_stream(self) -> None:
        self._buffer = []
    
    def feed_audio(self, chunk: np.ndarray) -> str:
        """Whisper 无流式，仅缓冲"""
        self._buffer.append(chunk.copy())
        return ""
    
    def end_stream(self, chunk: Optional[np.ndarray] = None) -> str:
        if chunk is not None:
            self._buffer.append(chunk.copy())
        if not self._buffer:
            return ""
        full = np.concatenate(self._buffer)
        self._buffer = []
        return self.recognize_audio(full, 16000)

    def recognize_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        import tempfile
        import wave
        import time as _time
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

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with open(tmp.name, "rb") as rf:
                        files = {"file": ("audio.wav", rf, "audio/wav")}
                        data = {"model": self.model}
                        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                        r = requests.post(
                            f"{self.api_base}/audio/transcriptions",
                            files=files,
                            data=data,
                            headers=headers,
                            timeout=30,
                        )
                    if r.status_code != 200:
                        raise RuntimeError(f"Whisper API 错误: {r.status_code} {r.text}")
                    return (r.json().get("text") or "").strip()
                except requests.exceptions.Timeout:
                    raise RuntimeError("Whisper API 请求超时（30秒）")
                except (requests.exceptions.ConnectionError, requests.exceptions.RequestException) as e:
                    if attempt < max_retries - 1:
                        wait = 0.5 * (2 ** attempt)
                        _time.sleep(wait)
                    else:
                        raise RuntimeError(f"Whisper API 请求失败: {e}")
            return ""
        finally:
            Path(tmp.name).unlink(missing_ok=True)


class FunASRRemoteProvider(ASRProvider):
    """
    远程 FunASR 服务（自建服务器）

    - 本地麦克风采集，发送到远程服务器识别
    - 不支持流式，录音结束整段发送
    - 比 Whisper API 更快，适合自建服务器
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5002",
        language: str = "zh",
        chunk_size: Optional[List[int]] = None,
    ):
        from backend.asr.remote_client import RemoteASRClient, RemoteASRConfig
        config = RemoteASRConfig(base_url=base_url, language=language)
        self._client = RemoteASRClient(config)
        self._chunk_size = chunk_size or [5, 10, 5]
        self._buffer: list = []

    @property
    def supports_streaming(self) -> bool:
        return False

    def get_chunk_stride(self) -> int:
        return self._chunk_size[1] * 960  # 与本地 FunASR 统一：10*960=9600 (600ms)

    def start_stream(self) -> None:
        # NOTE: caller must call start_stream to reclaim buffer memory on error paths
        self._buffer = []

    def feed_audio(self, chunk: np.ndarray) -> str:
        """缓冲音频，不支持实时流式"""
        self._buffer.append(chunk.copy())
        return ""

    def end_stream(self, chunk: Optional[np.ndarray] = None) -> str:
        if chunk is not None:
            self._buffer.append(chunk.copy())
        if not self._buffer:
            return ""
        full = np.concatenate(self._buffer)
        self._buffer = []
        return self.recognize_audio(full, 16000)

    def recognize_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        return self._client.recognize_audio(audio, sample_rate)

    def health_check(self) -> bool:
        """Check if remote ASR service is available"""
        return self._client.health_check()

    def stop(self):
        """关闭远程连接（与 FunASRWebSocketProvider 接口统一）"""
        self.close()

    def close(self):
        """Close the underlying HTTP session"""
        if hasattr(self._client, 'close'):
            self._client.close()


class FunASRWebSocketProvider(ASRProvider):
    """
    FunASR WebSocket 流式 ASR 客户端

    通过 WebSocket 长连接实现真正的流式识别。
    适配 FunASR real-time server（funasr bin/asr_online_server.py）。
    """

    def __init__(
        self,
        uri: str = "ws://localhost:10095",
        chunk_size: Optional[List[int]] = None,
        encoder_chunk_look_back: int = 4,
        decoder_chunk_look_back: int = 1,
        verify_ssl: bool = True,
        hotwords: str = "",
        hotword_weight: float = 10.0,
    ):
        self.uri = uri
        self._chunk_size = chunk_size or [5, 10, 5]
        self._enc_look_back = encoder_chunk_look_back
        self._dec_look_back = decoder_chunk_look_back
        self._client = _FunASRWSClient(
            uri, self._chunk_size,
            self._enc_look_back, self._dec_look_back,
            verify_ssl=verify_ssl,
            hotwords=hotwords,
            hotword_weight=hotword_weight,
        )
        self._client.start()

    @property
    def supports_streaming(self) -> bool:
        return True

    def get_chunk_stride(self) -> int:
        # chunk_size[1] * 960 = 10 * 960 = 9600 samples = 600ms per stride
        # FunASR 2-pass: chunk_size = [5, 10, 5], stride = 9600 samples (600ms)
        return self._chunk_size[1] * 960

    def start_stream(self) -> None:
        self._client.start_stream()

    def feed_audio(self, chunk: np.ndarray) -> str:
        return self._client.feed_audio(chunk)

    def end_stream(self, chunk: Optional[np.ndarray] = None) -> str:
        return self._client.end_stream(chunk)

    def recognize_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """批量识别：缓冲音频 → start → feed → end"""
        self._client.start_stream()
        # 分块发送
        stride = self.get_chunk_stride()
        audio_int16 = audio
        if audio.dtype == np.float32:
            audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        for i in range(0, len(audio_int16), stride):
            chunk = audio_int16[i:i + stride]
            self._client.feed_audio(chunk)
        return self._client.end_stream()

    def health_check(self, timeout: float = 5.0) -> bool:
        """Check if WebSocket connection is available"""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._client.connected:
                return True
            time.sleep(0.2)
        return False

    def stop(self):
        """关闭 WebSocket 连接"""
        if self._client is None:
            return
        self._client.stop()
        self._client = None


class _FunASRWSClient:
    """FunASR WebSocket 底层客户端（后台线程运行事件循环）"""

    def __init__(self, uri, chunk_size, enc_look_back, dec_look_back, verify_ssl=True, hotwords="", hotword_weight=10.0):
        self.uri = uri
        self._chunk_size = chunk_size
        self._enc_look_back = enc_look_back
        self._dec_look_back = dec_look_back
        self._verify_ssl = verify_ssl
        self._hotwords = hotwords
        self._hotword_weight = hotword_weight

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._connected = False
        self._running = False

        # 结果收集
        self._result_queue: queue.Queue = queue.Queue()
        self._last_text = ""

        # 流式回调（可选）
        self.on_partial_result: Optional[callable] = None

        # 日志
        try:
            from core.log import log as _log
            self._log = _log
        except ImportError:
            self._log = logging.getLogger(__name__)

    def start(self):
        """启动后台事件循环和连接"""
        if self._running:
            return
        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="FunASR-WS")
        self._thread.start()

    def stop(self):
        """停止连接和事件循环"""
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def connected(self) -> bool:
        return self._connected

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        """保持连接，断线自动重连"""
        first = True
        while self._running:
            try:
                await self._connect_and_listen()
                first = True  # 连接成功过，重置
            except Exception as e:
                self._connected = False
                if self._running:
                    level = self._log.warn if first else self._log.debug
                    level(f"[ASR-WS] 连接失败: {e}")
                    first = False
                    await asyncio.sleep(2)

    async def _connect_and_listen(self):
        """建立连接，发送配置，持续监听服务端消息"""
        import websockets
        import ssl as _ssl
        self._log.info(f"[ASR-WS] 连接: {self.uri}")

        # wss:// SSL 上下文
        ssl_ctx = None
        if self.uri.startswith("wss://"):
            ssl_ctx = _ssl.create_default_context()
            if not self._verify_ssl:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = _ssl.CERT_NONE

        async with websockets.connect(
            self.uri, max_size=2**22,
            ssl=ssl_ctx,
            open_timeout=10,
            close_timeout=5,
        ) as ws:
            self._ws = ws
            self._connected = True
            self._log.info(f"[ASR-WS] 已连接")

            # 发送初始配置（匹配 FunASR 2pass 服务端协议）
            config = {
                "mode": "2pass",
                "chunk_size": self._chunk_size,
                "chunk_interval": 10,
                "encoder_chunk_look_back": self._enc_look_back,
                "decoder_chunk_look_back": self._dec_look_back,
                "wav_name": "microphone",
                "is_speaking": True,
                "wav_format": "pcm",
                "audio_fs": 16000,
                "itn": True,
                "hotwords": self._hotwords,
            }
            await ws.send(json.dumps(config))

            # 持续接收服务端消息
            async for msg in ws:
                if isinstance(msg, str):
                    try:
                        data = json.loads(msg)
                        text = data.get("text", "")
                        is_final = data.get("is_final", False)
                        mode = data.get("mode", "")
                        if text:
                            self._last_text = text
                            if self.on_partial_result and not is_final:
                                try:
                                    self.on_partial_result(text)
                                except Exception:
                                    pass
                            if is_final:
                                self._result_queue.put(text)
                    except json.JSONDecodeError:
                        pass

        # async with 退出意味着连接已关闭（可能是优雅断开），
        # 必须清除 _connected 标志，否则 feed_audio 会向死 socket 发送数据
        self._connected = False
        self._ws = None

    def start_stream(self):
        """开始新一轮识别"""
        # 清空旧结果
        while not self._result_queue.empty():
            try:
                self._result_queue.get_nowait()
            except queue.Empty:
                break
        self._last_text = ""

    def feed_audio(self, chunk: np.ndarray) -> str:
        """发送音频块（非阻塞），返回当前累积结果"""
        if not self._connected or self._ws is None:
            return ""
        # 收集已有中间结果
        text = ""
        while not self._result_queue.empty():
            try:
                text = self._result_queue.get_nowait()
            except queue.Empty:
                break
        # float32 → int16 bytes
        pcm_bytes = self._to_pcm_bytes(chunk)
        try:
            # 非阻塞发送：fire-and-forget，不阻塞 VAD 循环
            asyncio.run_coroutine_threadsafe(
                self._ws.send(pcm_bytes), self._loop
            )
        except Exception as e:
            self._log.debug(f"[ASR-WS] 发送失败: {e}")
            return ""
        return text or self._last_text

    def end_stream(self, chunk: Optional[np.ndarray] = None) -> str:
        """结束当前识别，返回最终结果"""
        if chunk is not None:
            self.feed_audio(chunk)

        if not self._connected or self._ws is None:
            return ""

        # 发送结束信号
        try:
            end_msg = json.dumps({"is_speaking": False})
            asyncio.run_coroutine_threadsafe(
                self._ws.send(end_msg), self._loop
            ).result(timeout=2)
        except Exception as e:
            self._log.debug(f"[ASR-WS] 发送结束信号失败: {e}")

        # 等待最终结果（最多 5 秒，避免长时间阻塞）
        final_text = ""
        try:
            final_text = self._result_queue.get(timeout=5)
        except queue.Empty:
            if not self._connected:
                return self._last_text
            final_text = self._last_text

        return final_text

    def _to_pcm_bytes(self, audio: np.ndarray) -> bytes:
        if audio.dtype == np.float32:
            audio = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        return audio.tobytes()
