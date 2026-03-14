# -*- coding: utf-8 -*-
"""
音频输入输出管理
处理麦克风输入和扬声器输出
"""

import sys
import time
import wave
import threading
import queue
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass
from collections import deque

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

# 尝试导入音频库
try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False
    log.warn("sounddevice 未安装，请运行: pip install sounddevice")

try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False


@dataclass
class AudioConfig:
    """音频配置"""
    sample_rate: int = 16000      # 采样率
    channels: int = 1              # 声道数
    dtype: str = "float32"         # 数据类型（float32 值域 [-1,1]，ASR 模型需要）
    chunk_size: int = 9600         # 每次读取的样本数 (600ms at 16kHz，匹配 Paraformer 流式 chunk)
    silence_threshold: float = 0.008 # 静音阈值（RMS），会被自适应噪声底噪覆盖
    silence_duration: float = 1.0    # 静音持续时间（秒）触发结束
    max_duration: float = 30.0       # 最大录音时长（秒）
    # VAD 高级参数
    min_speech_chunks: int = 1       # 最少连续语音块数才算有效语音开始（降低以避免短语漏检）
    hangover_chunks: int = 2         # 语音结束后延长的块数（防止截断尾音）
    pre_buffer_chunks: int = 3       # 预缓冲块数，语音开始时回溯，防止开头吃字
    noise_floor_alpha: float = 0.05  # 噪声底噪平滑系数（越小越平滑）


class AudioInput:
    """
    麦克风输入管理
    
    支持:
    - 连续监听模式
    - 语音活动检测 (VAD)
    - 回调函数处理音频
    """
    
    def __init__(self, config: AudioConfig = None):
        self.config = config or AudioConfig()
        self._stream = None
        self._is_listening = False
        self._audio_buffer = queue.Queue()
        self._callbacks = []
        
        # VAD 状态
        self._is_speaking = False
        self._silence_start = None
        self._speech_buffer = []
        
        # 自适应噪声底噪
        self._noise_floor: float = 0.0
        self._noise_floor_initialized = False
        self._noise_calibration_chunks = 0
        
    def add_callback(self, callback: Callable[[np.ndarray], None]):
        """添加音频数据回调"""
        self._callbacks.append(callback)
    
    def start_listening(self):
        """开始监听麦克风"""
        if not HAS_SOUNDDEVICE:
            raise RuntimeError("sounddevice 未安装")
        
        if self._is_listening:
            return
        
        self._is_listening = True
        self._speech_buffer = []
        self._is_speaking = False
        self._silence_start = None
        
        # 重置噪声底噪校准
        self._noise_floor = 0.0
        self._noise_floor_initialized = False
        self._noise_calibration_chunks = 0
        
        def audio_callback(indata, frames, time_info, status):
            if status:
                log.debug(f"[AudioIO] 状态: {status}")
            
            # 复制数据避免覆盖，并展平为 1D
            audio_data = indata.copy().flatten()
            
            # float32 录制，值域已经是 [-1, 1]，无需额外转换
            
            # 放入缓冲区
            self._audio_buffer.put(audio_data)
            
            # 调用回调
            for callback in self._callbacks:
                try:
                    callback(audio_data)
                except Exception as e:
                    log.error(f"[AudioIO] 回调错误: {e}")
        
        self._stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype,
            blocksize=self.config.chunk_size,
            callback=audio_callback
        )
        self._stream.start()
        log.debug(f"麦克风监听已启动 (dtype={self.config.dtype}, chunk={self.config.chunk_size}, sr={self.config.sample_rate})")
    
    def stop_listening(self):
        """停止监听"""
        self._is_listening = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        log.debug("麦克风监听已停止")
    
    def get_audio_chunk(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """获取一个音频块"""
        try:
            return self._audio_buffer.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def _compute_rms(self, audio_chunk: np.ndarray) -> float:
        """计算音频块的 RMS 值"""
        if audio_chunk.dtype == np.int16:
            audio_float = audio_chunk.astype(np.float32) / 32768.0
        else:
            audio_float = audio_chunk
        return float(np.sqrt(np.mean(audio_float ** 2)))
    
    def _update_noise_floor(self, rms: float):
        """自适应更新噪声底噪估计"""
        alpha = self.config.noise_floor_alpha
        if not self._noise_floor_initialized:
            # 前几个块用于校准噪声底噪
            self._noise_calibration_chunks += 1
            if self._noise_calibration_chunks == 1:
                self._noise_floor = rms
            else:
                # 校准期间跳过异常高能量的 chunk（可能用户刚开口），避免底噪被高估
                if rms < self._noise_floor * 4.0:
                    self._noise_floor = self._noise_floor * 0.7 + rms * 0.3
            if self._noise_calibration_chunks >= 8:  # 8 个 chunk (~4.8s) 后完成校准，更稳定
                self._noise_floor_initialized = True
                log.debug(f"[VAD] 噪声底噪校准完成: {self._noise_floor:.5f}")
        else:
            # 只在静音时缓慢更新噪声底噪
            if rms < self._noise_floor * 2.0:
                self._noise_floor = self._noise_floor * (1 - alpha) + rms * alpha
    
    def detect_speech(self, audio_chunk: np.ndarray) -> bool:
        """检测是否有语音（自适应阈值）"""
        rms = self._compute_rms(audio_chunk)
        self._update_noise_floor(rms)
        
        # 动态阈值 = max(固定阈值, 噪声底噪 × 2.5)
        # 倍率过高会导致正常说话被判为静音（尤其有风扇/空调时）
        adaptive_threshold = max(self.config.silence_threshold, self._noise_floor * 2.5)
        return rms > adaptive_threshold
    
    def record_until_silence(
        self,
        on_speech_start: Callable = None,
        on_speech_end: Callable[[np.ndarray], None] = None,
        on_chunk: Callable[[np.ndarray], None] = None,
    ):
        """
        录音直到检测到静音
        
        使用自适应 VAD：
        - 前几个 chunk 自动校准噪声底噪
        - 连续 min_speech_chunks 个语音块才算真正开始
        - 语音结束后有 hangover 延续，防止截断尾音
        - 静音段也会发给 on_chunk（保证 ASR 流式上下文完整）
        
        Args:
            on_speech_start: 检测到语音开始时的回调
            on_speech_end: 检测到语音结束时的回调，参数为完整音频
            on_chunk: 每个音频块的回调（用于流式 ASR）
        """
        if not self._is_listening:
            self.start_listening()
        
        speech_buffer = []
        is_speaking = False
        silence_start = None
        start_time = time.time()
        
        # 连续语音块计数（用于防止噪声尖峰误触发）
        consecutive_speech = 0
        # hangover 计数（语音结束后继续录制几个块）
        hangover_remaining = 0
        
        # 预缓冲：保留最近 N 个 chunk，语音开始时回溯，避免开头吃字
        pre_buffer = deque(maxlen=self.config.pre_buffer_chunks)
        
        while self._is_listening:
            chunk = self.get_audio_chunk(timeout=0.5)
            if chunk is None:
                continue
            
            has_speech = self.detect_speech(chunk)
            current_time = time.time()
            
            # 检查最大时长
            if current_time - start_time > self.config.max_duration:
                if speech_buffer and on_speech_end:
                    full_audio = np.concatenate(speech_buffer)
                    on_speech_end(full_audio)
                break
            
            if has_speech:
                consecutive_speech += 1
                hangover_remaining = self.config.hangover_chunks  # 重置 hangover
                
                if not is_speaking and consecutive_speech >= self.config.min_speech_chunks:
                    # 连续语音块达到阈值，确认语音开始
                    is_speaking = True
                    silence_start = None
                    log.debug("[VAD] 语音开始")
                    
                    # 将预缓冲中的 chunk 回溯加入，防止语音开头被截掉
                    for pre_chunk in pre_buffer:
                        speech_buffer.append(pre_chunk)
                        if on_chunk:
                            on_chunk(pre_chunk)
                    pre_buffer.clear()
                    
                    if on_speech_start:
                        on_speech_start()
                
                if is_speaking:
                    speech_buffer.append(chunk)
                    if on_chunk:
                        on_chunk(chunk)
                else:
                    # 还没确认语音开始（consecutive 不够），暂存预缓冲
                    pre_buffer.append(chunk)
                    
            else:
                consecutive_speech = 0  # 重置连续计数
                
                if is_speaking:
                    # 语音中的静音段：也要发给 ASR 保持上下文
                    speech_buffer.append(chunk)
                    if on_chunk:
                        on_chunk(chunk)
                    
                    # hangover 机制
                    if hangover_remaining > 0:
                        hangover_remaining -= 1
                        continue
                    
                    if silence_start is None:
                        silence_start = current_time
                    elif current_time - silence_start > self.config.silence_duration:
                        # 静音超过阈值，语音结束
                        log.debug(f"[VAD] 语音结束 (时长 {current_time - start_time:.1f}s)")
                        if on_speech_end and speech_buffer:
                            full_audio = np.concatenate(speech_buffer)
                            on_speech_end(full_audio)
                        break
                else:
                    # 未开始说话，保存到预缓冲
                    pre_buffer.append(chunk)
        
        return np.concatenate(speech_buffer) if speech_buffer else None


class AudioOutput:
    """
    扬声器输出管理
    
    支持:
    - 播放音频文件
    - 播放音频数组
    - 流式播放
    """
    
    def __init__(self, sample_rate: int = 22050):
        self.sample_rate = sample_rate
        self._is_playing = False
        self._play_thread = None
        self._stop_flag = threading.Event()
        self._play_queue = queue.Queue()
    
    def play_file(self, file_path: str, blocking: bool = True):
        """播放音频文件"""
        if not HAS_SOUNDDEVICE:
            raise RuntimeError("sounddevice 未安装")
        
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {file_path}")
        
        # 读取音频
        if HAS_SOUNDFILE:
            data, sr = sf.read(str(file_path))
        else:
            # 使用 wave 模块
            with wave.open(str(file_path), 'rb') as wf:
                sr = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        
        self.play_array(data, sr, blocking)
    
    def play_array(self, audio: np.ndarray, sample_rate: int = None, blocking: bool = True):
        """播放音频数组"""
        if not HAS_SOUNDDEVICE:
            raise RuntimeError("sounddevice 未安装")
        
        sr = sample_rate or self.sample_rate
        self._is_playing = True
        
        if blocking:
            sd.play(audio, sr)
            sd.wait()
            self._is_playing = False
        else:
            def play_thread():
                sd.play(audio, sr)
                sd.wait()
                self._is_playing = False
            
            self._play_thread = threading.Thread(target=play_thread, daemon=True)
            self._play_thread.start()
    
    def play_stream(self, audio_generator, sample_rate: int = None):
        """
        流式播放音频
        
        Args:
            audio_generator: 生成音频块的迭代器
            sample_rate: 采样率
        """
        if not HAS_SOUNDDEVICE:
            raise RuntimeError("sounddevice 未安装")
        
        sr = sample_rate or self.sample_rate
        self._is_playing = True
        self._stop_flag.clear()
        
        def stream_callback(outdata, frames, time_info, status):
            if status:
                print(f"[AudioIO] 播放状态: {status}")
            
            try:
                chunk = self._play_queue.get_nowait()
                if len(chunk) < frames:
                    outdata[:len(chunk), 0] = chunk
                    outdata[len(chunk):] = 0
                else:
                    outdata[:, 0] = chunk[:frames]
            except queue.Empty:
                outdata.fill(0)
        
        # 填充队列
        def fill_queue():
            for chunk in audio_generator:
                if self._stop_flag.is_set():
                    break
                self._play_queue.put(chunk)
            self._is_playing = False
        
        fill_thread = threading.Thread(target=fill_queue, daemon=True)
        fill_thread.start()
        
        with sd.OutputStream(
            samplerate=sr,
            channels=1,
            callback=stream_callback
        ):
            while self._is_playing and not self._stop_flag.is_set():
                time.sleep(0.1)
    
    def stop(self):
        """停止播放"""
        self._stop_flag.set()
        sd.stop()
        self._is_playing = False
    
    def is_playing(self) -> bool:
        """是否正在播放"""
        return self._is_playing


# 便捷函数
def play_audio(file_or_array, sample_rate: int = 22050, blocking: bool = True):
    """播放音频（文件或数组）"""
    output = AudioOutput(sample_rate)
    if isinstance(file_or_array, (str, Path)):
        output.play_file(str(file_or_array), blocking)
    else:
        output.play_array(file_or_array, sample_rate, blocking)
