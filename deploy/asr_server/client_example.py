#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ASR 服务器客户端示例
演示如何调用各个 API
"""

import requests
import base64
import wave
import numpy as np
from pathlib import Path


class ASRClient:
    """ASR 服务器客户端"""
    
    def __init__(self, base_url="http://localhost:5002"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except:
            return False
    
    def _audio_file_to_base64(self, audio_path: str) -> str:
        """将音频文件转换为 base64"""
        with open(audio_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def _array_to_base64(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """将 numpy 数组转换为 base64 WAV"""
        import io
        
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
            wav_bytes = f.getvalue()
        
        return base64.b64encode(wav_bytes).decode('utf-8')
    
    def recognize(self, audio_path: str = None, audio: np.ndarray = None, sample_rate: int = 16000) -> dict:
        """ASR 识别"""
        if audio_path:
            audio_b64 = self._audio_file_to_base64(audio_path)
        elif audio is not None:
            audio_b64 = self._array_to_base64(audio, sample_rate)
        else:
            raise ValueError("必须提供 audio_path 或 audio")
        
        resp = self.session.post(
            f"{self.base_url}/asr/recognize",
            json={"audio": audio_b64, "sample_rate": sample_rate},
            timeout=30
        )
        return resp.json()
    
    def recognize_emotion(self, audio_path: str = None, audio: np.ndarray = None, sample_rate: int = 16000) -> dict:
        """SER 情绪识别"""
        if audio_path:
            audio_b64 = self._audio_file_to_base64(audio_path)
        elif audio is not None:
            audio_b64 = self._array_to_base64(audio, sample_rate)
        else:
            raise ValueError("必须提供 audio_path 或 audio")
        
        resp = self.session.post(
            f"{self.base_url}/ser/recognize",
            json={"audio": audio_b64},
            timeout=30
        )
        return resp.json()
    
    def extract_voiceprint(self, audio_path: str = None, audio: np.ndarray = None, sample_rate: int = 16000) -> dict:
        """SV 声纹提取"""
        if audio_path:
            audio_b64 = self._audio_file_to_base64(audio_path)
        elif audio is not None:
            audio_b64 = self._array_to_base64(audio, sample_rate)
        else:
            raise ValueError("必须提供 audio_path 或 audio")
        
        resp = self.session.post(
            f"{self.base_url}/sv/extract",
            json={"audio": audio_b64},
            timeout=30
        )
        return resp.json()
    
    def identify_speaker(self, audio_path: str = None, audio: np.ndarray = None, sample_rate: int = 16000) -> dict:
        """Diarization 说话人识别"""
        if audio_path:
            audio_b64 = self._audio_file_to_base64(audio_path)
        elif audio is not None:
            audio_b64 = self._array_to_base64(audio, sample_rate)
        else:
            raise ValueError("必须提供 audio_path 或 audio")
        
        resp = self.session.post(
            f"{self.base_url}/diarization/identify",
            json={"audio": audio_b64},
            timeout=30
        )
        return resp.json()
    
    def restore_punctuation(self, text: str) -> dict:
        """PUNC 标点恢复"""
        resp = self.session.post(
            f"{self.base_url}/punc/restore",
            json={"text": text},
            timeout=10
        )
        return resp.json()
    
    def detect_voice_activity(self, audio_path: str = None, audio: np.ndarray = None, sample_rate: int = 16000) -> dict:
        """VAD 语音活动检测"""
        if audio_path:
            audio_b64 = self._audio_file_to_base64(audio_path)
        elif audio is not None:
            audio_b64 = self._array_to_base64(audio, sample_rate)
        else:
            raise ValueError("必须提供 audio_path 或 audio")
        
        resp = self.session.post(
            f"{self.base_url}/vad/detect",
            json={"audio": audio_b64},
            timeout=10
        )
        return resp.json()
    
    def process_all(
        self,
        audio_path: str = None,
        audio: np.ndarray = None,
        sample_rate: int = 16000,
        enable_ser: bool = True,
        enable_diarization: bool = True,
        enable_punc: bool = True
    ) -> dict:
        """一站式处理"""
        if audio_path:
            audio_b64 = self._audio_file_to_base64(audio_path)
        elif audio is not None:
            audio_b64 = self._array_to_base64(audio, sample_rate)
        else:
            raise ValueError("必须提供 audio_path 或 audio")
        
        resp = self.session.post(
            f"{self.base_url}/all/process",
            json={
                "audio": audio_b64,
                "enable_ser": enable_ser,
                "enable_diarization": enable_diarization,
                "enable_punc": enable_punc
            },
            timeout=60
        )
        return resp.json()


def main():
    """示例用法"""
    client = ASRClient("http://localhost:5002")
    
    # 1. 健康检查
    print("=" * 60)
    print("1. 健康检查")
    print("=" * 60)
    if client.health_check():
        print("✓ ASR 服务可用")
    else:
        print("✗ ASR 服务不可用")
        return
    
    # 2. ASR 识别示例
    print("\n" + "=" * 60)
    print("2. ASR 识别")
    print("=" * 60)
    
    # 生成测试音频（1秒正弦波）
    sample_rate = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration))
    test_audio = np.sin(2 * np.pi * 440 * t).astype(np.float32) * 0.3
    
    # 如果有真实音频文件，可以这样用：
    # result = client.recognize(audio_path="test.wav")
    
    # 使用 numpy 数组：
    result = client.recognize(audio=test_audio, sample_rate=sample_rate)
    print(f"识别结果: {result}")
    
    # 3. 标点恢复示例
    print("\n" + "=" * 60)
    print("3. 标点恢复")
    print("=" * 60)
    
    text = "你好我是小明今天天气真好"
    result = client.restore_punctuation(text)
    print(f"原文: {text}")
    print(f"恢复后: {result.get('text')}")
    
    # 4. 一站式处理示例
    print("\n" + "=" * 60)
    print("4. 一站式处理")
    print("=" * 60)
    
    result = client.process_all(
        audio=test_audio,
        sample_rate=sample_rate,
        enable_ser=True,
        enable_diarization=False,  # 需要先注册说话人
        enable_punc=True
    )
    print(f"处理结果: {result}")


if __name__ == "__main__":
    main()
