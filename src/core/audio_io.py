# -*- coding: utf-8 -*-
"""
音频输入输出管理
处理麦克风输入和扬声器输出
"""

import logging
import sys
import time
import wave
import threading
import queue
from pathlib import Path
from typing import Callable, Optional, Union
from dataclasses import dataclass
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)

try:
    from core.log import log
except ImportError:
    class _Fallback:
        @staticmethod
        def debug(msg): logger.debug(msg)
        @staticmethod
        def info(msg): logger.info(msg)
        @staticmethod
        def warn(msg): logger.warning(msg)
        @staticmethod
        def error(msg): logger.error(msg)
    log = _Fallback()

from core.vad import VADConfig, create_vad, VADBackend

try:
    from core.config_manager import InterruptConfig
except ImportError:
    InterruptConfig = None

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
    chunk_size: int = 9600          # 每次读取的样本数 (600ms at 16kHz，匹配 Paraformer chunk [0,10,5])
    max_duration: float = 30.0       # 最大录音时长（秒）
    # VAD 配置（可用 VADConfig 或兼容的 kwargs）
    vad_config: Optional[VADConfig] = None
    # 兼容旧参数（当 vad_config 为 None 时使用）
    silence_threshold: float = 0.008
    silence_duration: float = 0.6
    min_speech_chunks: int = 1
    hangover_chunks: int = 1
    pre_buffer_chunks: int = 2
    noise_floor_alpha: float = 0.05
    vad_backend: str = "rms"  # "rms" | "silero"


class AudioInput:
    """
    麦克风输入管理
    
    支持:
    - 连续监听模式
    - 语音活动检测 (VAD)：RMS 或 Silero 后端
    - 回调函数处理音频
    """
    
    def __init__(self, config: AudioConfig = None):
        self.config = config or AudioConfig()
        self._stream = None
        self._is_listening = False
        self._running = threading.Event()
        self._audio_buffer = queue.Queue()
        self._callbacks = []

        # VAD 状态
        self._is_speaking = False
        self._silence_start = None
        self._speech_buffer = []

        # 构建 VADConfig 与后端
        self._vad_config = self._build_vad_config()
        self._vad: VADBackend = create_vad(self._vad_config)
        log.debug(f"[AudioIO] VAD 后端: {self._vad_config.backend}")

        # 打断检测状态（P0-2）
        self._interrupt_active = threading.Event()
        self._interrupt_vad: Optional[VADBackend] = None
        self._interrupt_callback: Optional[Callable] = None
        self._interrupt_speech_ms = 0
        self._interrupt_min_speech_ms = 300
        self._interrupt_speech_start: Optional[float] = None

    def update_interrupt_config(self, min_speech_ms: int = None):
        """Public API to update interrupt detection parameters (thread-safe)."""
        if min_speech_ms is not None:
            self._interrupt_min_speech_ms = min_speech_ms

    def _build_vad_config(self) -> VADConfig:
        """从 AudioConfig 构建 VADConfig"""
        if self.config.vad_config is not None:
            return self.config.vad_config
        return VADConfig(
            backend=self.config.vad_backend,
            silence_duration=self.config.silence_duration,
            min_speech_chunks=self.config.min_speech_chunks,
            hangover_chunks=self.config.hangover_chunks,
            pre_buffer_chunks=self.config.pre_buffer_chunks,
            silence_threshold=self.config.silence_threshold,
            noise_floor_alpha=self.config.noise_floor_alpha,
        )
        
    def add_callback(self, callback: Callable[[np.ndarray], None]):
        """添加音频数据回调"""
        self._callbacks.append(callback)
    
    def start_listening(self):
        """开始监听麦克风"""
        if not HAS_SOUNDDEVICE:
            raise RuntimeError("sounddevice 未安装")
        
        # NOTE: _is_listening is read/written without a lock; this is a benign
        # race because the worst case is a double-start that gets caught by the
        # stream creation.  A full lock would add complexity for no real gain.
        if self._is_listening:
            return

        self._is_listening = True
        self._running.set()
        self._speech_buffer = []
        self._is_speaking = False
        self._silence_start = None
        self._vad.reset()
        
        def audio_callback(indata, frames, time_info, status):
            if status:
                log.debug(f"[AudioIO] 状态: {status}")

            # 复制数据避免覆盖，并展平为 1D
            audio_data = indata.copy().flatten()

            # float32 录制，值域已经是 [-1, 1]，无需额外转换

            # 放入缓冲区
            self._audio_buffer.put(audio_data)

            # 打断检测（P0-2）
            self._process_interrupt_audio(audio_data)

            # 调用回调
            for callback in list(self._callbacks):
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
        self._running.clear()
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        log.debug("麦克风监听已停止")

    def pause_for_tts(self):
        """暂停麦克风（TTS 播报期间防止回声拾取）。"""
        if self._stream and self._is_listening:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            log.debug("[AudioIO] mic paused for TTS")
        else:
            log.debug(f"[AudioIO] mic pause skipped (stream={self._stream is not None}, listening={self._is_listening})")

    def resume_after_tts(self):
        """TTS 播报完毕后恢复麦克风。"""
        if not self._is_listening:
            log.debug("[AudioIO] mic resume skipped (not listening)")
            return
        if self._stream is not None:
            log.debug("[AudioIO] mic resume skipped (stream already active)")
            return  # 已在运行
        flushed = self.flush_buffer()
        self._vad.reset()
        # 等待驱动缓冲区排空后二次清空，防止 TTS 残留音频混入下一轮录音
        # 扬声器尾音/房间混响常 >50ms，过短易导致下一句 ASR 吃到「了、因为」等碎片
        time.sleep(0.22)
        flushed2 = self.flush_buffer()
        log.debug(f"[AudioIO] mic resuming (flushed {flushed}+{flushed2} stale chunks)")

        def audio_callback(indata, frames, time_info, status):
            if status:
                log.debug(f"[AudioIO] 状态: {status}")
            audio_data = indata.copy().flatten()
            self._audio_buffer.put(audio_data)
            # 打断检测（P0-2）
            self._process_interrupt_audio(audio_data)
            for cb in list(self._callbacks):
                try:
                    cb(audio_data)
                except Exception as e:
                    log.error(f"[AudioIO] 回调错误: {e}")

        self._stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype,
            blocksize=self.config.chunk_size,
            callback=audio_callback,
        )
        self._stream.start()
        try:
            dropped = self._discard_input_until_quiet()
            if dropped:
                self.flush_buffer()
        except Exception as e:
            log.debug(f"[AudioIO] post-TTS quiet discard skipped: {e}")
        log.debug("[AudioIO] mic resumed after TTS")
    
    def start_interrupt_detection(
        self,
        on_interrupt: Callable,
        config: "InterruptConfig" = None,
    ):
        """启动打断检测（TTS 播报期间）。

        麦克风保持开启（不调用 pause_for_tts），使用独立 VAD 实例
        检测用户语音活动。检测到持续语音超过阈值时触发 on_interrupt 回调。
        """
        if config is None:
            from core.config_manager import get_config_manager
            config = get_config_manager().config.interrupt

        self._interrupt_active.set()
        self._interrupt_callback = on_interrupt
        self._interrupt_min_speech_ms = config.min_speech_ms
        self._interrupt_speech_ms = 0
        self._interrupt_speech_start = None

        # 创建独立 VAD 实例（避免与主监听 VAD 冲突）
        int_vad_cfg = VADConfig(
            backend=self._vad_config.backend,
            silence_duration=config.min_speech_ms / 1000.0,
            min_speech_chunks=1,
            hangover_chunks=1,
            pre_buffer_chunks=0,
            silence_threshold=self._vad_config.silence_threshold,
        )
        self._interrupt_vad = create_vad(int_vad_cfg)
        log.debug(f"[AudioIO] interrupt detection started (min_speech={config.min_speech_ms}ms)")

    def stop_interrupt_detection(self):
        """停止打断检测"""
        self._interrupt_active.clear()
        self._interrupt_vad = None
        self._interrupt_callback = None
        self._interrupt_speech_start = None
        self._interrupt_speech_ms = 0
        log.debug("[AudioIO] interrupt detection stopped")

    def _process_interrupt_audio(self, audio_data: np.ndarray):
        """处理打断检测音频（在 audio_callback 中调用）"""
        if not self._interrupt_active.is_set():
            return
        # Snapshot the vad reference to avoid race with stop_interrupt_detection()
        vad = self._interrupt_vad
        if vad is None:
            return
        try:
            has_speech = vad.detect_speech(audio_data, self.config.sample_rate)
            now = time.time()
            if has_speech:
                if self._interrupt_speech_start is None:
                    self._interrupt_speech_start = now
                    log.debug("[AudioIO] interrupt: speech detected, waiting for threshold...")
                elapsed_ms = (now - self._interrupt_speech_start) * 1000
                if elapsed_ms >= self._interrupt_min_speech_ms:
                    log.info(f"[AudioIO] interrupt triggered! ({elapsed_ms:.0f}ms >= {self._interrupt_min_speech_ms}ms)")
                    self._interrupt_active.clear()  # 防止重复触发
                    if self._interrupt_callback:
                        try:
                            self._interrupt_callback()
                        except Exception as e:
                            log.error(f"[AudioIO] interrupt callback error: {e}")
            else:
                # 静音重置计时
                self._interrupt_speech_start = None
        except Exception as e:
            log.debug(f"[AudioIO] interrupt processing error: {e}")

    def get_audio_chunk(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """获取一个音频块"""
        try:
            return self._audio_buffer.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush_buffer(self, max_items: int = 4096) -> int:
        """
        清空内部音频队列，避免积压的旧音频影响下一次录音。
        返回清空的 chunk 数。
        """
        n = 0
        while n < max_items:
            try:
                self._audio_buffer.get_nowait()
                n += 1
            except queue.Empty:
                break
        return n

    def _discard_input_until_quiet(
        self,
        max_seconds: float = 0.55,
        rms_thresh: float = 0.018,
        need_quiet_chunks: int = 4,
        chunk_timeout: float = 0.08,
    ) -> int:
        """
        从输入队列读块并丢弃，直到连续若干块 RMS 低于门限。

        用于 TTS 刚结束、麦克风刚恢复时，把扬声器尾音/混响从队列里清掉，
        减轻下一句 ASR 吃到「了、因为」等上一句碎片。
        """
        deadline = time.time() + max_seconds
        quiet_run = 0
        drained = 0
        while time.time() < deadline and self._is_listening:
            chunk = self.get_audio_chunk(timeout=chunk_timeout)
            if chunk is None:
                continue
            drained += 1
            arr = np.asarray(chunk, dtype=np.float64).ravel()
            if arr.size == 0:
                continue
            rms = float(np.sqrt(np.mean(arr * arr)))
            if rms < rms_thresh:
                quiet_run += 1
                if quiet_run >= need_quiet_chunks:
                    break
            else:
                quiet_run = 0
        if drained > 0:
            log.debug(
                f"[AudioIO] post-TTS discard: dropped {drained} chunks, quiet_run={quiet_run}"
            )
        return drained

    def _drain_straggler_audio_chunks(self, max_rounds: int = 48, empty_sleep_s: float = 0.02):
        """
        句末后尽量排空声卡回调仍往队列里塞的旧块，避免下一轮 VAD 的 pre_buffer 混入上一句尾巴。
        """
        idle = 0
        for _ in range(max_rounds):
            try:
                self._audio_buffer.get_nowait()
                idle = 0
            except queue.Empty:
                idle += 1
                if idle >= 4:
                    break
                time.sleep(empty_sleep_s)
    
    def detect_speech(self, audio_chunk: np.ndarray) -> bool:
        """检测是否有语音（由 VAD 后端实现）"""
        return self._vad.detect_speech(audio_chunk, self.config.sample_rate)

    @staticmethod
    def _speech_buffer_duration_sec(speech_buffer: list, sample_rate: int) -> float:
        """已缓冲语音的大致时长（秒），用于句中防误切。"""
        if not speech_buffer:
            return 0.0
        n = 0
        for c in speech_buffer:
            n += int(np.asarray(c).size)
        return n / float(max(1, sample_rate))

    def _effective_endpoint_silence_sec(self, vc: "VADConfig", speech_buffer: list) -> float:
        """累计语音仍较短时用更长静音才判停，减轻句中换气被切成两句。"""
        base = float(vc.silence_duration)
        min_v = float(
            getattr(vc, "min_voice_accum_sec_for_fast_endpoint", 0.0) or 0.0
        )
        mid_s = float(getattr(vc, "mid_utterance_silence_sec", 0.0) or 0.0)
        if min_v <= 0 or mid_s <= 0:
            return base
        voice_accum = self._speech_buffer_duration_sec(
            speech_buffer, self.config.sample_rate
        )
        if voice_accum < min_v:
            eff = max(base, mid_s)
            if eff > base:
                log.debug(
                    f"[VAD] 判停静音阈值延长至 {eff:.2f}s（已录≈{voice_accum:.2f}s < {min_v:.2f}s）"
                )
            return eff
        return base
    
    def record_until_silence(
        self,
        on_speech_start: Callable = None,
        on_speech_end: Callable[[np.ndarray], None] = None,
        on_chunk: Callable[[np.ndarray], None] = None,
        cancel_event: threading.Event = None,
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

        # 关键：清掉上一轮/空闲期间积压的旧音频，否则会"回放式"地先处理旧 chunk，导致延迟与误判
        flushed = self.flush_buffer()
        if flushed:
            log.debug(f"[AudioIO] flush_buffer: {flushed} chunks")

        # 每次录音前重置 VAD，避免噪声底噪/状态在多轮之间漂移
        try:
            self._vad.reset()
        except Exception:
            logger.debug("Failed to reset VAD state before recording", exc_info=True)

        # 等待声卡驱动缓冲区排空（sounddevice 内部 ring buffer 常有数十 ms 残留）
        # 然后二次清空，彻底消除上一轮语音残留
        time.sleep(0.20)
        flushed2 = self.flush_buffer()
        if flushed2:
            log.debug(f"[AudioIO] flush_buffer(2nd): {flushed2} chunks")
        
        speech_buffer = []
        is_speaking = False
        silence_start = None
        start_time = time.time()
        
        vc = self._vad_config
        consecutive_speech = 0
        hangover_remaining = 0
        pre_buffer = deque(maxlen=vc.pre_buffer_chunks)
        tail_pad_active = False
        tail_pad_deadline: Optional[float] = None

        while self._is_listening:
            # 检查外部取消
            if cancel_event and cancel_event.is_set():
                log.debug("[audio] recording cancelled by external event")
                break
            if not self._running:
                break
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
                hangover_remaining = vc.hangover_chunks
                
                if not is_speaking and consecutive_speech >= vc.min_speech_chunks:
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
                    # 句中再次出现语音：取消句尾缓冲计时，避免短静音误用旧的 silence_start
                    silence_start = None
                    tail_pad_active = False
                    tail_pad_deadline = None
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
                        tail_pad_active = False
                        tail_pad_deadline = None
                    elif tail_pad_active:
                        if tail_pad_deadline is not None and current_time >= tail_pad_deadline:
                            log.debug(
                                f"[VAD] 语音结束 (句尾缓冲后 {current_time - start_time:.1f}s)"
                            )
                            if on_speech_end and speech_buffer:
                                full_audio = np.concatenate(speech_buffer)
                                on_speech_end(full_audio)
                            break
                    elif current_time - silence_start > self._effective_endpoint_silence_sec(
                        vc, speech_buffer
                    ):
                        # 静音已达判停阈值：再进入句尾缓冲，收录弱语气词等
                        tail_pad = float(
                            getattr(vc, "endpoint_tail_padding_sec", 0.48) or 0.0
                        )
                        if tail_pad > 0:
                            tail_pad_active = True
                            tail_pad_deadline = current_time + tail_pad
                            log.debug(
                                f"[VAD] 已达静音判停，句尾再录 {tail_pad:.2f}s"
                            )
                        else:
                            log.debug(
                                f"[VAD] 语音结束 (时长 {current_time - start_time:.1f}s)"
                            )
                            if on_speech_end and speech_buffer:
                                full_audio = np.concatenate(speech_buffer)
                                on_speech_end(full_audio)
                            break
                else:
                    # 未开始说话，保存到预缓冲
                    pre_buffer.append(chunk)

        # 句末后再排一队尾块，减轻「下一句 pre_buffer 吃到上一句」的串音
        try:
            self._drain_straggler_audio_chunks()
        except Exception as e:
            log.debug(f"[AudioIO] drain stragglers: {e}")

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
            try:
                sd.play(audio, sr)
                sd.wait()
            finally:
                self._is_playing = False
        else:
            def play_thread():
                try:
                    sd.play(audio, sr)
                    sd.wait()
                finally:
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
                logger.warning(f"[AudioIO] 播放状态: {status}")
            
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
            try:
                for chunk in audio_generator:
                    if self._stop_flag.is_set():
                        break
                    self._play_queue.put(chunk)
            except Exception as e:
                logger.error(f"[AudioIO] fill_queue error: {e}")
            finally:
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
        # Drain stale chunks so they don't play on the next call
        while not self._play_queue.empty():
            try:
                self._play_queue.get_nowait()
            except queue.Empty:
                break
    
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
