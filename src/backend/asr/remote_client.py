# -*- coding: utf-8 -*-
"""
远程 ASR 客户端
通过 HTTP API 调用远程/云端 ASR 服务
"""

import requests
import base64
import numpy as np
import io
import wave
import time
from typing import Optional
from dataclasses import dataclass

try:
    from core.log import log
except ImportError:
    # 独立运行时的回退
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


@dataclass
class RemoteASRConfig:
    """远程 ASR 配置"""
    base_url: str = ""  # ASR 服务地址（如 "http://server:5002"）
    timeout: int = 30  # 请求超时（秒）
    language: str = "zh"  # 语言代码


class RemoteASRClient:
    """
    远程 ASR 客户端

    支持两种模式：
    1. 批量模式：录音完成后一次性发送识别
    2. 流式模式：边录边发，实时返回识别结果（如果服务端支持）
    """

    def __init__(self, config: RemoteASRConfig = None):
        if config is None:
            try:
                from core.settings import AppSettings
                s = AppSettings.load()
                config = RemoteASRConfig(base_url=s.remote_asr_url)
            except Exception as e:
                import logging
                logging.warning(f"加载 ASR 配置失败，使用默认值: {e}")
                config = RemoteASRConfig(base_url="http://localhost:5002")
        elif not config.base_url:
            try:
                from core.settings import AppSettings
                s = AppSettings.load()
                config.base_url = s.remote_asr_url  # type: ignore[misc]
            except Exception as e:
                import logging
                logging.warning(f"加载 ASR URL 失败，使用默认值: {e}")
                config.base_url = "http://localhost:5002"  # type: ignore[misc]
        self.config = config
        self._session: Optional[requests.Session] = None
        self._buffer = []  # 用于流式模式的音频缓冲

    def _get_session(self) -> requests.Session:
        """获取或创建 HTTP Session（懒初始化）"""
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def close(self):
        """关闭 HTTP Session，释放资源"""
        if self._session is not None:
            self._session.close()
            self._session = None

    def __del__(self):
        """析构时关闭 Session"""
        self.close()

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, *args):
        """上下文管理器出口"""
        self.close()

    @property
    def base_url(self) -> str:
        return self.config.base_url.rstrip('/')

    def health_check(self) -> bool:
        """检查 ASR 服务是否可用"""
        try:
            resp = self._get_session().get(
                f"{self.base_url}/health",
                timeout=5
            )
            return resp.status_code == 200
        except Exception:
            return False

    def recognize_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """
        识别音频（批量模式）
        
        Args:
            audio: 音频数据（float32, mono）
            sample_rate: 采样率
            
        Returns:
            识别文本
        """
        try:
            # 转换为 WAV 格式
            wav_bytes = self._array_to_wav_bytes(audio, sample_rate)
            
            # Base64 编码
            audio_b64 = base64.b64encode(wav_bytes).decode('utf-8')
            
            # 发送请求
            resp = self._get_session().post(
                f"{self.base_url}/asr/recognize",
                json={
                    "audio": audio_b64,
                    "sample_rate": sample_rate,
                    "language": self.config.language,
                },
                timeout=self.config.timeout
            )
            
            if resp.status_code != 200:
                log.error(f"[远程ASR] 请求失败: {resp.status_code} - {resp.text}")
                return ""
            
            data = resp.json()
            if data.get("status") != "success":
                log.error(f"[远程ASR] 识别失败: {data.get('error')}")
                return ""
            
            text = data.get("text", "").strip()
            log.debug(f"[远程ASR] 识别结果: {text}")
            return text
            
        except requests.Timeout:
            log.error("[远程ASR] 请求超时")
            return ""
        except Exception as e:
            log.error(f"[远程ASR] 错误: {e}")
            return ""
    
    def start_stream(self) -> None:
        """开始流式识别"""
        self._buffer = []
    
    def feed_audio(self, chunk: np.ndarray) -> str:
        """
        喂入音频块（流式模式）
        
        Args:
            chunk: 音频块
            
        Returns:
            实时识别结果（如果服务端支持流式）
        """
        self._buffer.append(chunk.copy())
        # 远程 ASR 通常不支持真正的流式，这里只是缓冲
        return ""
    
    def end_stream(self, chunk: Optional[np.ndarray] = None) -> str:
        """
        结束流式识别
        
        Args:
            chunk: 最后一个音频块
            
        Returns:
            完整识别结果
        """
        if chunk is not None:
            self._buffer.append(chunk)
        
        if not self._buffer:
            return ""
        
        # 合并所有音频块
        full_audio = np.concatenate(self._buffer)
        self._buffer = []
        
        # 批量识别
        return self.recognize_audio(full_audio, 16000)
    
    def _array_to_wav_bytes(self, audio: np.ndarray, sample_rate: int) -> bytes:
        """将 numpy 数组转换为 WAV 字节"""
        # 转换为 int16
        if audio.dtype == np.float32:
            audio = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        
        # 写入 WAV
        with io.BytesIO() as f:
            with wave.open(f, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio.tobytes())
            return f.getvalue()


# === 便捷函数 ===

def create_remote_asr(
    url: str = "http://localhost:5002",
    language: str = "zh"
) -> RemoteASRClient:
    """
    创建远程 ASR 客户端
    
    Args:
        url: ASR 服务地址（本地或云端）
        language: 语言代码
        
    Returns:
        RemoteASRClient 实例
    """
    config = RemoteASRConfig(
        base_url=url,
        language=language
    )
    return RemoteASRClient(config)


if __name__ == "__main__":
    # 测试
    client = create_remote_asr("http://localhost:5002")
    
    if client.health_check():
        print("ASR 服务可用")
        
        # 测试识别（需要准备测试音频）
        # test_audio = np.random.randn(16000).astype(np.float32)  # 1秒测试音频
        # result = client.recognize_audio(test_audio, 16000)
        # print(f"识别结果: {result}")
    else:
        print("ASR 服务不可用")
