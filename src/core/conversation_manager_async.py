# -*- coding: utf-8 -*-
"""
异步对话管理器（学习 Yione 架构）
整合 ASR + Agent + TTS 实现完整对话流程，支持流式打断

核心设计：
1. 基于 asyncio.Task 的可取消架构
2. TTS Worker + Pending Queue 解耦
3. 智能句子切分（硬切 + 软切）
4. 去重和防抖机制
"""

import asyncio
import contextlib
import re
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

import numpy as np

from core.audio_io import AudioInput, AudioOutput, AudioConfig
from core.vad import VADConfig
from core.log import log
from core.emotion_classifier import EmotionClassifier
from core.ser_engine import SEREngine, SERResult
from core.punc_engine import PUNCEngine
from core.sv_engine import SVEngine, SVResult
from core.performance_metrics import (
    PerformanceMonitor,
    ASRMetrics,
    TTSMetrics,
    InterruptMetrics,
)
from core.tts_cache import TTSCache
from core.config_manager import SystemConfig, get_config_manager

# 导入 conversation 模块
from core.conversation import ConversationState, ConversationConfig, TurnMetrics
from core.conversation.sentence_splitter import pop_sentence as _pop_sentence

# 添加路径
project_root = Path(__file__).parent.parent.parent


# ============================================================
#  Turn 状态（学习 Yione）
# ============================================================

@dataclass
class _TurnState:
    """LLM 循环 + TTS worker 共享的 turn 级状态"""
    t0: float
    next_idx: int = 0
    last_motion_emotion: str | None = None
    current_emotion: str = "neutral"
    sentences_queued: int = 0


@dataclass
class _PendingSentence:
    """推进 TTS worker 的载荷：一句话 + 它已评估好的情绪"""
    text: str
    emotion: str


# 队列里的 None 表示"没有更多句子了，worker 可以收摊"
_PendingItem = _PendingSentence | None


# ============================================================
#  异步对话管理器
# ============================================================

class AsyncConversationManager:
    """
    异步对话管理器（学习 Yione 架构）
    
    核心特性:
    1. 基于 asyncio.Task 的可取消架构
    2. TTS Worker + Pending Queue 解耦
    3. 智能句子切分
    4. 去重机制
    """
    
    def __init__(self, config: SystemConfig = None):
        self.config = config or get_config_manager().config
        self.state = ConversationState.IDLE
        
        # 组件（延迟初始化）
        self._asr = None
        self._tts = None
        self._tts_mode = None
        self._agent = None
        self._audio_input = None
        self._audio_output = None
        
        # 回调
        self._on_state_change: Optional[Callable] = None
        self._on_user_text: Optional[Callable] = None
        self._on_ai_text: Optional[Callable] = None
        self._on_subtitle: Optional[Callable] = None
        self._on_audio_rms: Optional[Callable] = None
        self._on_viseme: Optional[Callable] = None
        self._on_exit_requested: Optional[Callable] = None
        
        # 情绪状态
        self._current_emotion: str = "neutral"
        self._emotion_classifier = EmotionClassifier()
        self._current_user_emotion: str = "neutral"
        self._ser: SEREngine | None = None
        self._punc: PUNCEngine | None = None
        self._sv: SVEngine | None = None
        
        # 多说话人识别
        self._diarization = None
        self._current_user_id: str = self.config.general.user_id
        self._on_speaker_change_callback: Optional[Callable] = None
        
        # Turn 管理（学习 Yione）
        self._current_turn: asyncio.Task | None = None
        
        # 打断统计
        self._interrupt_count: int = 0
        
        # 去重机制（学习 Yione）
        self._last_submitted: dict[str, float] = {}  # text -> timestamp
        self._dedup_window_ms: int = 2000
        
        # 性能监控
        self._perf_monitor: PerformanceMonitor = PerformanceMonitor()
        self._current_turn_start: float = 0.0
        self._current_turn_id: str = ""
        
        # TTS 缓存
        self._tts_cache: Optional[TTSCache] = None

        # 文字输入队列（由 tray 对话框 / message_server 投递）
        self._user_text_queue: asyncio.Queue | None = None

        # 运行状态（使用 threading.Event 保证线程安全）
        self._running = threading.Event()
    
    # ============================================================
    #  初始化方法（从同步版本迁移）
    # ============================================================
    
    def _get_asr_stream_profile(self) -> dict:
        """根据配置返回 ASR 流式参数档位"""
        profile = (self.config.asr.stream_profile or "balanced").strip().lower()
        presets = {
            "low_latency": {
                "chunk_size": [0, 8, 4],
                "encoder_chunk_look_back": 4,
                "decoder_chunk_look_back": 1,
            },
            "balanced": {
                "chunk_size": [0, 10, 5],
                "encoder_chunk_look_back": 4,
                "decoder_chunk_look_back": 1,
            },
            "accuracy": {
                "chunk_size": [0, 10, 5],
                "encoder_chunk_look_back": 6,
                "decoder_chunk_look_back": 2,
            },
        }
        return presets.get(profile, presets["balanced"])
    
    def _resolve_asr_device(self, requested: str) -> str:
        """解析 ASR 设备：支持 auto 自动选择 CUDA/CPU"""
        req = (requested or "auto").strip().lower()

        def _cuda_available() -> bool:
            try:
                import torch
                return bool(torch.cuda.is_available())
            except Exception:
                return False

        def _cuda_count() -> int:
            try:
                import torch
                return int(torch.cuda.device_count())
            except Exception:
                return 0

        if req == "auto":
            return "cuda:0" if _cuda_available() else "cpu"

        if req == "cuda":
            req = "cuda:0"

        if req.startswith("cuda"):
            if not _cuda_available():
                log.warn(f"ASR 指定设备 '{requested}' 不可用，已回退到 cpu")
                return "cpu"
            m = re.fullmatch(r"cuda:(\d+)", req)
            if m:
                idx = int(m.group(1))
                count = _cuda_count()
                if 0 <= idx < max(1, count):
                    return req
                fallback = "cuda:0" if count > 0 else "cpu"
                log.warn(f"ASR 指定设备 '{requested}' 越界（GPU 数量={count}），已回退到 {fallback}")
                return fallback
            if req == "cuda":
                return "cuda:0"
            log.warn(f"ASR 指定设备 '{requested}' 不可用，已回退到 cpu")
            return "cpu"

        return "cpu"
    
    def _init_asr(self):
        """初始化 ASR（FunASR 本地或 Whisper 远程）"""
        if self._asr is not None:
            return
        
        if self.config.general.use_text_input:
            log.debug("[对话] 使用文字输入模式，跳过 ASR 初始化")
            self._asr = None
            return
        
        provider = (self.config.asr.provider or "funasr").lower()
        
        if provider == "whisper":
            try:
                from backend.asr.providers import WhisperRemoteProvider
                base = self.config.asr.whisper_api_base or "https://api.openai.com/v1"
                key = self.config.asr.whisper_api_key or ""
                self._asr = WhisperRemoteProvider(api_base=base, api_key=key)
                log.debug("[对话] ASR: Whisper 远程模式")
            except Exception as e:
                log.warn(f"Whisper ASR 初始化失败: {e}")
                self._asr = None
            return
        
        # FunASR 本地
        try:
            from backend.asr.providers import FunASRProvider
            
            model_dir = self.config.asr.model_dir
            if not model_dir:
                try:
                    from core.settings import AppSettings
                    s = AppSettings.load()
                    if s.asr_model_dir.exists():
                        model_dir = str(s.asr_model_dir)
                except Exception:
                    pass
                for p in [
                    project_root / "models" / "ASR" / "paraformer-zh-streaming",
                ]:
                    if p.exists():
                        model_dir = str(p)
                        break
            
            vad_model = None
            if self.config.audio.use_vad:
                try:
                    from core.settings import AppSettings
                    s = AppSettings.load()
                    if s.asr_vad_dir.exists():
                        vad_model = str(s.asr_vad_dir)
                except Exception:
                    pass
                for p in [
                    project_root / "models" / "ASR" / "fsmn-vad",
                ]:
                    if p.exists():
                        vad_model = str(p)
                        break
                vad_model = vad_model or "fsmn-vad"
            
            if model_dir and Path(model_dir).exists():
                asr_device = self._resolve_asr_device(self.config.asr.device)
                stream_cfg = self._get_asr_stream_profile()
                self._asr = FunASRProvider(
                    model_dir=model_dir,
                    vad_model=vad_model,
                    device=asr_device,
                    chunk_size=stream_cfg.get("chunk_size"),
                    encoder_chunk_look_back=stream_cfg.get("encoder_chunk_look_back"),
                    decoder_chunk_look_back=stream_cfg.get("decoder_chunk_look_back"),
                )
                log.debug(
                    f"[对话] ASR: FunASR 本地模式 (device={asr_device}, "
                    f"chunk={stream_cfg.get('chunk_size')})"
                )
            else:
                log.warn(f"ASR 模型目录不存在: {model_dir}")
                self._asr = None
        except Exception as e:
            log.warn(f"ASR 初始化失败: {e}")
            self._asr = None
    
    def _init_tts(self):
        """初始化 TTS（支持本地和远程模式）"""
        if self._tts is not None:
            return
        
        # 优先使用远程 TTS
        if self.config.tts.remote_url:
            try:
                from backend.tts.remote_client import RemoteTTSClient, RemoteTTSConfig
                
                remote_config = RemoteTTSConfig(
                    base_url=self.config.tts.remote_url,
                    spk_id=self.config.tts.spk_id,
                )
                client = RemoteTTSClient(remote_config)
                
                if client.health_check():
                    self._tts = client
                    self._tts_mode = "remote"
                    log.debug(f"[对话] TTS 远程服务初始化完成: {self.config.tts.remote_url}")
                    return
                else:
                    log.warn(f"TTS 远程服务不可用: {self.config.tts.remote_url}")
            except Exception as e:
                log.warn(f"TTS 远程服务初始化失败: {e}")
        
        # 本地 TTS
        try:
            from backend.tts.engine import CosyvoiceRealTimeTTS
            
            model_dir = self.config.tts.model_dir
            if not model_dir:
                default_paths = [
                    project_root / "models" / "TTS" / "CosyVoice2-0.5B",
                ]
                try:
                    from core.settings import AppSettings
                    s = AppSettings.load()
                    if s.tts_model_dir.exists():
                        default_paths.insert(0, s.tts_model_dir)
                except Exception:
                    pass
                for p in default_paths:
                    if p.exists():
                        model_dir = str(p)
                        break
            
            if model_dir and Path(model_dir).exists():
                self._tts = CosyvoiceRealTimeTTS(model_path=model_dir)
                self._tts_mode = "local"
                log.debug("[对话] TTS 本地引擎初始化完成")
            else:
                log.warn(f"TTS 模型目录不存在: {model_dir}")
                self._tts = None
                self._tts_mode = None
        except Exception as e:
            log.warn(f"TTS 初始化失败: {e}")
            self._tts = None
            self._tts_mode = None
        
        # 初始化 TTS 缓存
        if self._tts and self.config.tts.enable_cache:
            try:
                cache_dir = project_root / "cache" / "tts" if self.config.tts.enable_cache else None
                self._tts_cache = TTSCache(
                    max_size=self.config.tts.cache_size,
                    cache_dir=cache_dir,
                    enable_disk_cache=False,  # 暂时禁用磁盘缓存
                )
                log.debug(f"[对话] TTS 缓存初始化完成 (大小: {self.config.tts.cache_size})")
                
                # 预加载常用短语
                if self.config.tts.cache_common_phrases:
                    log.info(f"[对话] 预加载 {len(self.config.tts.cache_common_phrases)} 个常用短语...")
                    # 注意：预加载需要在后台线程中进行，避免阻塞初始化
                    # 这里暂时跳过，可以在首次使用时按需加载
            except Exception as e:
                log.warn(f"TTS 缓存初始化失败: {e}")
                self._tts_cache = None
    
    def _init_agent(self):
        """初始化 Agent"""
        if self._agent is not None:
            return
        
        try:
            from backend.llm.agent import Agent
            
            self._agent = Agent(user_id=self.config.general.user_id)
            self._agent.start_chat()
            log.debug("[对话] Agent 初始化完成")
        except Exception as e:
            log.error(f"Agent 初始化失败: {e}")
            raise
    
    def _init_audio(self):
        """初始化音频设备"""
        self._init_asr()
        
        chunk_size = 5760  # 默认 360ms
        if self._asr and hasattr(self._asr, "get_chunk_stride"):
            chunk_size = self._asr.get_chunk_stride()
        
        vad_config = VADConfig.preset(self.config.audio.vad_preset)
        vad_config.backend = self.config.audio.vad_backend
        vad_config.silence_duration = self.config.audio.silence_duration
        vad_config.min_speech_chunks = max(2, vad_config.min_speech_chunks)
        vad_config.hangover_chunks = max(1, vad_config.hangover_chunks)
        vad_config.pre_buffer_chunks = max(2, vad_config.pre_buffer_chunks)
        
        audio_config = AudioConfig(
            sample_rate=self.config.audio.sample_rate,
            dtype="float32",
            chunk_size=chunk_size,
            vad_config=vad_config,
            vad_backend=self.config.audio.vad_backend,
        )
        self._audio_input = AudioInput(audio_config)
        self._audio_output = AudioOutput()
        log.debug("[对话] 音频设备初始化完成")
    
    def initialize(self):
        """初始化所有组件"""
        log.debug("[对话] 正在初始化异步对话系统...")
        self._init_audio()
        self._init_tts()
        self._init_agent()
        log.info("异步对话系统初始化完成")
    
    # ============================================================
    #  回调管理
    # ============================================================
    
    def set_callbacks(
        self,
        on_state_change: Callable[[ConversationState], None] = None,
        on_user_text: Callable[[str], None] = None,
        on_ai_text: Callable[[str], None] = None,
        on_subtitle: Callable[[str, bool, str], None] = None,
        on_audio_rms: Callable[[float], None] = None,
        on_viseme: Callable[[float, float], None] = None,
        on_exit_requested: Callable[[str], None] = None,
    ):
        """设置回调函数"""
        self._on_state_change = on_state_change
        self._on_user_text = on_user_text
        self._on_ai_text = on_ai_text
        self._on_subtitle = on_subtitle
        self._on_audio_rms = on_audio_rms
        self._on_viseme = on_viseme
        self._on_exit_requested = on_exit_requested
    
    # ============================================================
    #  状态管理
    # ============================================================
    
    def _set_state(self, state: ConversationState):
        """设置状态"""
        old_state = self.state
        self.state = state
        log.debug(f"[对话] 状态: {old_state.value} → {state.value}")
        if self._on_state_change:
            self._on_state_change(state)
    
    def _send_subtitle(self, text: str, is_final: bool = False, emotion: str = "neutral"):
        """发送字幕"""
        if self._on_subtitle:
            self._on_subtitle(text, is_final, emotion)
    
    # ============================================================
    #  TTS Worker（学习 Yione）
    # ============================================================
    
    async def _tts_worker(
        self,
        pending: asyncio.Queue[_PendingItem],
        state: _TurnState,
    ) -> None:
        """消费 pending，每拿到一句就调 TTS，产生音频播放。
        
        None 是结束哨兵。被 cancel() 时也会自然向上抛 CancelledError。
        """
        while True:
            item = await pending.get()
            if item is None:
                return
            
            try:
                # 性能监控
                t_tts_start = time.monotonic()
                t_first_chunk = None
                total_audio_duration = 0.0
                chunk_count = 0
                
                first = True
                # 使用流式 TTS 生成（在线程中运行）
                def _sync_tts_gen():
                    """同步 TTS 生成器"""
                    for chunk_data in self._tts.generate_audio_streaming(
                        item.text, use_clone=True, max_workers=2
                    ):
                        yield chunk_data
                
                # 在线程池中运行 TTS 生成
                for chunk_data in await asyncio.to_thread(list, _sync_tts_gen()):
                    if len(chunk_data) == 4:
                        audio, seg_idx, total, visemes = chunk_data
                    else:
                        audio, seg_idx, total = chunk_data[:3]
                        visemes = None
                    
                    state.next_idx += 1
                    chunk_count += 1
                    
                    if first:
                        t_first_chunk = time.monotonic()
                        t_first = t_first_chunk - state.t0
                        log.info(
                            f"[{t_first:.2f}s] TTS 首包: {item.text[:20]}... → idx={state.next_idx}"
                        )
                        first = False
                    
                    # 计算音频时长
                    audio_duration = len(audio) / max(1, self._tts.sample_rate)
                    total_audio_duration += audio_duration
                    
                    # 播放音频（在线程中阻塞）
                    await asyncio.to_thread(
                        self._audio_output.play_array,
                        audio,
                        self._tts.sample_rate,
                        blocking=True
                    )
                    
                    # 发送嘴型数据
                    if visemes and self._on_viseme:
                        asyncio.create_task(
                            self._send_visemes_async(visemes, audio, self._tts.sample_rate)
                        )
                    elif self._on_audio_rms:
                        asyncio.create_task(
                            self._send_rms_async(audio, self._tts.sample_rate)
                        )
                
                # 记录 TTS 性能
                t_tts_end = time.monotonic()
                if t_first_chunk:
                    first_chunk_latency_ms = (t_first_chunk - t_tts_start) * 1000
                    total_latency_ms = (t_tts_end - t_tts_start) * 1000
                    audio_duration_ms = total_audio_duration * 1000
                    rtf = total_latency_ms / audio_duration_ms if audio_duration_ms > 0 else 0.0
                    
                    metrics = TTSMetrics(
                        first_chunk_latency_ms=first_chunk_latency_ms,
                        total_latency_ms=total_latency_ms,
                        rtf=rtf,
                        audio_duration_ms=audio_duration_ms,
                        text_length=len(item.text),
                        chunk_count=chunk_count,
                    )
                    self._perf_monitor.record_tts(metrics)
                    
                    log.debug(
                        f"[TTS 性能] 首包: {first_chunk_latency_ms:.1f}ms, "
                        f"总延迟: {total_latency_ms:.1f}ms, RTF: {rtf:.3f}"
                    )
                
            except Exception as exc:
                log.error(f"TTS 播放失败: {exc}")
    
    # Rhubarb 口型映射
    VISEME_SHAPE_MAP = {
        'X': (0.00, 0.00),   # 闭嘴
        'A': (0.05, 0.00),   # 口型很小
        'B': (0.25, 0.60),   # 双唇轻合
        'C': (0.50, 0.20),   # 中等开口
        'D': (0.85, 0.40),   # 大张口
        'E': (0.55, -0.40),  # 圆嘴
        'F': (0.35, -0.70),  # 窄嘴
        'G': (0.20, 0.30),   # 轻开口
        'H': (0.40, 0.10),   # 中等开口
    }
    
    async def _send_visemes_async(self, visemes, audio, sample_rate):
        """异步发送 viseme 数据"""
        try:
            if not visemes:
                return
            audio_duration = len(audio) / max(1, sample_rate)
            t0 = time.monotonic()
            interval = 1.0 / 30  # 30fps
            
            cue_idx = 0
            current_shape = 'X'
            elapsed = 0.0
            
            while elapsed < audio_duration:
                while cue_idx < len(visemes) - 1:
                    next_start = visemes[cue_idx + 1].get('start', 999)
                    if elapsed >= next_start:
                        cue_idx += 1
                    else:
                        break
                
                current_shape = visemes[cue_idx].get('value', 'X')
                openY, form = self.VISEME_SHAPE_MAP.get(current_shape, (0.0, 0.0))
                
                if self._on_viseme:
                    # 在线程中调用同步回调
                    await asyncio.to_thread(self._on_viseme, openY, form)
                
                await asyncio.sleep(interval)
                elapsed = time.monotonic() - t0
            
            # 结束时发送闭嘴
            if self._on_viseme:
                await asyncio.to_thread(self._on_viseme, 0.0, 0.0)
        except Exception as e:
            log.debug(f"Viseme 发送错误: {e}")
    
    async def _send_rms_async(self, audio, sample_rate):
        """异步发送 RMS 数据"""
        try:
            window_ms = 50
            window_samples = max(1, int(sample_rate * window_ms / 1000))
            
            audio_float = audio.astype(np.float32)
            max_val = np.max(np.abs(audio_float))
            if max_val > 1.0:
                audio_float = audio_float / 32768.0
            
            for i in range(0, len(audio_float), window_samples):
                window = audio_float[i:i + window_samples]
                rms = float(np.sqrt(np.mean(window ** 2)))
                if self._on_audio_rms:
                    await asyncio.to_thread(self._on_audio_rms, rms)
                await asyncio.sleep(window_ms / 1000.0)
        except Exception as e:
            log.debug(f"RMS 发送错误: {e}")
    
    # ============================================================
    #  Turn 处理（学习 Yione）
    # ============================================================
    
    async def _handle_user_message(self, user_text: str) -> None:
        """一次完整的用户 turn。被 cancel() 时在 finally 里清理 worker 并发 idle。"""
        t0 = time.monotonic()
        self._current_turn_start = t0
        self._current_turn_id = f"turn_{int(t0 * 1000)}"
        
        log.info(f"[0.00s] 用户消息: {user_text[:40]}...")
        
        self._set_state(ConversationState.PROCESSING)
        
        pending: asyncio.Queue[_PendingItem] = asyncio.Queue()
        state = _TurnState(t0=t0)
        worker = asyncio.create_task(self._tts_worker(pending, state))
        
        # 两份缓冲：raw 保留 LLM 原始输出（含标签），clean 是剥掉标签后的字幕文本
        raw = ""
        clean = ""
        unspoken = ""  # clean 里还没入 TTS 队列的部分
        first_chunk = True
        
        # 性能监控
        t_llm_first = None
        t_tts_first = None
        interrupted = False
        
        try:
            # 流式获取 Agent 回复
            async for chunk in self._stream_agent_reply(user_text):
                if first_chunk:
                    t_llm_first = time.monotonic()
                    log.info(f"[{t_llm_first - t0:.2f}s] LLM 首包: {chunk[:20]}...")
                    first_chunk = False
                
                raw += chunk
                new_clean, last_tag = self._strip_emotion_tags(raw)
                if last_tag is not None:
                    state.current_emotion = last_tag
                
                delta = new_clean[len(clean):]
                clean = new_clean
                unspoken += delta
                
                # 发送中间字幕
                self._send_subtitle(clean, is_final=False, emotion=state.current_emotion)
                
                # 切分句子
                while True:
                    sentence, unspoken = _pop_sentence(unspoken)
                    if sentence is None:
                        break
                    
                    # 评估句子情绪
                    sentence_emotion = self._emotion_classifier.classify(sentence).emotion
                    if sentence_emotion != "neutral":
                        state.current_emotion = sentence_emotion
                    
                    state.sentences_queued += 1
                    
                    # 记录 TTS 首包时间
                    if t_tts_first is None and state.sentences_queued == 1:
                        t_tts_first = time.monotonic()
                    
                    log.info(
                        f"[{time.monotonic() - t0:.2f}s] 队列句子 #{state.sentences_queued} "
                        f"({state.current_emotion}): {sentence[:30]}..."
                    )
                    await pending.put(_PendingSentence(text=sentence, emotion=state.current_emotion))
            
            log.info(
                f"[{time.monotonic() - t0:.2f}s] LLM 完成, "
                f"clean={len(clean)} chars, unspoken={unspoken[:40]}..."
            )
            
            # 发送最终字幕
            self._send_subtitle(clean, is_final=True, emotion=state.current_emotion)
            
            # 剩余文本入队
            if unspoken.strip():
                state.sentences_queued += 1
                await pending.put(_PendingSentence(text=unspoken, emotion=state.current_emotion))
            
            # 通知 worker 结束
            await pending.put(None)
            self._set_state(ConversationState.SPEAKING)
            await worker
            
            log.info(f"[{time.monotonic() - t0:.2f}s] 所有段播放完成")
            self._set_state(ConversationState.IDLE)
            
            # 记录 Turn 性能
            t_end = time.monotonic()
            turn_metrics = TurnMetrics(
                turn_id=self._current_turn_id,
                user_text=user_text,
                ai_text=clean,
                llm_first_token_ms=(t_llm_first - t0) * 1000 if t_llm_first else 0.0,
                llm_total_ms=(t_end - t0) * 1000,
                tts_first_chunk_ms=(t_tts_first - t0) * 1000 if t_tts_first else 0.0,
                total_latency_ms=(t_end - t0) * 1000,
                interrupted=interrupted,
            )
            self._perf_monitor.record_turn(turn_metrics)
            
        except asyncio.CancelledError:
            # 被打断：清空待合成句、停掉 worker、发 idle
            interrupted = True
            t_end = time.monotonic()
            log.info(f"[{t_end - t0:.2f}s] Turn 被打断")
            
            # 记录打断的 Turn 性能
            turn_metrics = TurnMetrics(
                turn_id=self._current_turn_id,
                user_text=user_text,
                ai_text=clean,
                llm_first_token_ms=(t_llm_first - t0) * 1000 if t_llm_first else 0.0,
                llm_total_ms=(t_end - t0) * 1000,
                tts_first_chunk_ms=(t_tts_first - t0) * 1000 if t_tts_first else 0.0,
                total_latency_ms=(t_end - t0) * 1000,
                interrupted=True,
            )
            self._perf_monitor.record_turn(turn_metrics)
            
            self._drain_queue(pending)
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker
            with contextlib.suppress(Exception):
                self._set_state(ConversationState.IDLE)
            raise
        except Exception:
            log.exception("Turn 失败")
            self._drain_queue(pending)
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker
            with contextlib.suppress(Exception):
                self._set_state(ConversationState.IDLE)
            raise
    
    def _drain_queue(self, q: asyncio.Queue[_PendingItem]) -> None:
        """把队列里未处理的项丢掉"""
        try:
            while True:
                q.get_nowait()
        except asyncio.QueueEmpty:
            return
    
    async def _stream_agent_reply(self, user_text: str) -> AsyncIterator[str]:
        """流式获取 Agent 回复（异步包装）"""
        if not self._agent:
            yield "抱歉，AI 服务未初始化"
            return

        # 创建队列用于线程间通信
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        exception_holder = [None]

        # 捕获当前事件循环引用（修复 Python 3.12+ 兼容性问题）
        loop = asyncio.get_running_loop()

        def _sync_generator():
            """在线程中运行同步生成器"""
            try:
                for chunk in self._agent.chat(user_text, stream=True):
                    # 使用捕获的 loop 引用调用 call_soon_threadsafe
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as e:
                log.error(f"Agent 流式生成错误: {e}")
                exception_holder[0] = e
            finally:
                # 发送结束信号
                loop.call_soon_threadsafe(queue.put_nowait, None)

        # 在线程池中启动同步生成器
        asyncio.create_task(asyncio.to_thread(_sync_generator))
        
        # 异步消费队列
        while True:
            chunk = await queue.get()
            if chunk is None:
                if exception_holder[0]:
                    raise exception_holder[0]
                break
            yield chunk
    
    async def _listen_and_recognize_async(self) -> Optional[str]:
        """异步监听并识别语音"""
        # 文字输入队列模式（tray 对话框 / message_server 投递）
        if self._user_text_queue is not None:
            try:
                return await asyncio.wait_for(self._user_text_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                return None

        if self._asr:
            try:
                # 使用 asyncio.to_thread 包装同步 ASR
                return await asyncio.to_thread(self._listen_with_asr)
            except Exception as e:
                log.warn(f"ASR 识别异常: {e}")
                return await asyncio.to_thread(self._listen_with_text)
        return await asyncio.to_thread(self._listen_with_text)
    
    def _listen_with_asr(self) -> Optional[str]:
        """使用 ASR 监听麦克风（同步方法，由 asyncio.to_thread 调用）"""
        log.info("🎤 请说话...")
        
        # 性能监控
        t_start = time.monotonic()
        t_first_chunk = None
        audio_start = None
        
        streaming_parts = []
        merged_stream_ref = [""]
        last_partial_ref = [""]
        full_audio_ref = [None]
        supports_streaming = getattr(self._asr, "supports_streaming", False)

        def on_speech_start():
            nonlocal audio_start
            audio_start = time.monotonic()
            log.debug("检测到语音...")

        def on_chunk(chunk):
            nonlocal t_first_chunk
            if self._asr:
                result = self._asr.feed_audio(chunk)
                if result and supports_streaming:
                    if t_first_chunk is None:
                        t_first_chunk = time.monotonic()
                    part = result.strip()
                    if part and part != last_partial_ref[0]:
                        last_partial_ref[0] = part
                        streaming_parts.append(part)
                        merged_stream_ref[0] = self._merge_streaming_pair(merged_stream_ref[0], part)
                        log.debug(f"[ASR] 中间: '{merged_stream_ref[0]}'")

        def on_speech_end(full_audio):
            full_audio_ref[0] = full_audio

        self._asr.start_stream()
        
        self._audio_input.record_until_silence(
            on_speech_start=on_speech_start,
            on_chunk=on_chunk,
            on_speech_end=on_speech_end,
        )
        
        full_audio = full_audio_ref[0]
        final = (self._asr.end_stream() or "").strip()
        merged_stream = merged_stream_ref[0] or self._merge_streaming_results(streaming_parts)
        
        if supports_streaming and not final:
            final = merged_stream
        elif supports_streaming and merged_stream and len(merged_stream) > len(final) + 1 and final in merged_stream:
            final = merged_stream
        
        # 记录性能指标
        t_end = time.monotonic()
        if final and audio_start:
            audio_duration_ms = (t_end - audio_start) * 1000
            total_latency_ms = (t_end - t_start) * 1000
            first_chunk_latency_ms = (t_first_chunk - t_start) * 1000 if t_first_chunk else total_latency_ms
            rtf = total_latency_ms / audio_duration_ms if audio_duration_ms > 0 else 0.0
            
            metrics = ASRMetrics(
                first_chunk_latency_ms=first_chunk_latency_ms,
                total_latency_ms=total_latency_ms,
                rtf=rtf,
                audio_duration_ms=audio_duration_ms,
                text_length=len(final),
            )
            self._perf_monitor.record_asr(metrics)
            
            log.debug(
                f"[ASR 性能] 首包: {first_chunk_latency_ms:.1f}ms, "
                f"总延迟: {total_latency_ms:.1f}ms, RTF: {rtf:.3f}"
            )
        
        if final:
            log.debug(f"[ASR] 最终: '{final}'")
        return final or None
    
    def _listen_with_text(self) -> Optional[str]:
        """使用文本输入（调试模式）"""
        try:
            text = input("\n👤 请输入 (或说 'quit' 退出): ").strip()
            return text if text else None
        except EOFError:
            return None

    def submit_user_text(self, text: str):
        """从任意线程投递用户文字到对话循环（线程安全）"""
        # 先捕获引用，避免竞态条件
        queue = self._user_text_queue
        if queue is not None:
            try:
                queue.put_nowait(text)
            except asyncio.QueueFull:
                log.warning("用户文本队列已满，丢弃消息")
            except Exception as e:
                log.warning(f"投递用户文本失败: {e}")
    
    @staticmethod
    def _merge_streaming_pair(base: str, incoming: str) -> str:
        """合并两段流式文本"""
        b = (base or "").strip()
        p = (incoming or "").strip()
        if not p:
            return b
        if not b:
            return p
        if p.startswith(b):
            return p
        if b.startswith(p):
            return b
        max_overlap = min(len(b), len(p))
        for i in range(max_overlap, 0, -1):
            if b.endswith(p[:i]):
                return b + p[i:]
        return b + p
    
    def _merge_streaming_results(self, parts: list) -> str:
        """合并流式识别结果"""
        merged = ""
        for p in parts or []:
            merged = self._merge_streaming_pair(merged, p)
        return merged
    
    def _strip_emotion_tags(self, text: str) -> tuple[str, str | None]:
        """剥离情绪标签，返回 (clean_text, first_emotion)"""
        pattern = re.compile(r'\[(joy|anger|sadness|surprise|neutral|shy|think|fear|cry)\]', re.IGNORECASE)
        emotions_found = pattern.findall(text)
        # 取第一个情绪标签
        first_tag = emotions_found[0].lower() if emotions_found else None
        clean_text = pattern.sub("", text).strip()
        clean_text = re.sub(r'  +', ' ', clean_text)
        return clean_text, first_tag
    
    # ============================================================
    #  Turn 管理（学习 Yione）
    # ============================================================
    
    async def cancel_current_turn(self) -> None:
        """取消当前 turn"""
        t = self._current_turn
        if t is None or t.done():
            return
        
        # 性能监控
        t_interrupt_start = time.monotonic()
        
        log.info("[打断] 取消当前 turn")
        self._interrupt_count += 1
        
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t
        self._current_turn = None
        
        # 记录打断性能
        t_interrupt_end = time.monotonic()
        response_time_ms = (t_interrupt_end - t_interrupt_start) * 1000
        
        interrupt_metrics = InterruptMetrics(
            response_time_ms=response_time_ms,
            detection_latency_ms=0.0,  # 暂时为 0，后续可以添加检测延迟
            stop_latency_ms=response_time_ms,
            interrupted_at_ms=(t_interrupt_start - self._current_turn_start) * 1000 if self._current_turn_start else 0.0,
            total_duration_ms=(t_interrupt_end - self._current_turn_start) * 1000 if self._current_turn_start else 0.0,
        )
        self._perf_monitor.record_interrupt(interrupt_metrics)
        
        # 显示打断反馈
        if self.config.interrupt.feedback_enabled:
            self._send_subtitle("⚠️ 已打断", is_final=True, emotion="neutral")
        
        log.info(f"[打断统计] 总打断次数: {self._interrupt_count}, 响应时间: {response_time_ms:.1f}ms")
    
    def run_turn(self, user_text: str) -> None:
        """启动新的 turn"""
        self._current_turn = asyncio.create_task(self._handle_user_message(user_text))
    
    # ============================================================
    #  去重机制（学习 Yione）
    # ============================================================
    
    def _should_submit(self, text: str) -> bool:
        """检查是否应该提交（去重）"""
        now = time.time() * 1000  # 毫秒
        last_time = self._last_submitted.get(text)
        
        if last_time and (now - last_time) < self._dedup_window_ms:
            log.debug(f"[去重] 忽略重复文本: {text[:30]}...")
            return False
        
        self._last_submitted[text] = now
        
        # 清理过期记录
        cutoff = now - self._dedup_window_ms * 2
        self._last_submitted = {
            k: v for k, v in self._last_submitted.items() if v > cutoff
        }
        
        return True
    
    # ============================================================
    #  主循环
    # ============================================================
    
    async def run_async(self):
        """异步主循环"""
        log.info("\n异步对话系统已启动\n")
        self._running.set()

        # 文字输入模式：创建队列供外部投递
        if self.config.general.use_text_input:
            self._user_text_queue = asyncio.Queue()
            log.info("[文字输入] 队列已创建，等待外部投递...")

        while self._running.is_set():
            try:
                # 监听用户输入
                self._set_state(ConversationState.LISTENING)
                user_text = await self._listen_and_recognize_async()
                
                if not user_text:
                    continue
                
                if user_text.lower() in ['quit', 'exit', '退出', '结束']:
                    log.debug("收到退出指令")
                    break
                
                # 去重检查
                if not self._should_submit(user_text):
                    continue
                
                print(f"\n👤 用户: {user_text}")
                if self._on_user_text:
                    self._on_user_text(user_text)
                
                # 如果有正在进行的 turn，先打断
                await self.cancel_current_turn()
                
                # 启动新 turn
                self.run_turn(user_text)
                
                # 等待 turn 完成
                if self._current_turn:
                    try:
                        await self._current_turn
                    except asyncio.CancelledError:
                        pass  # 被打断是正常的
                
            except KeyboardInterrupt:
                print("\n用户中断")
                break
            except Exception as e:
                log.error(f"对话错误: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(1)
        
        log.info("异步对话循环已退出")
    
    # ============================================================
    #  性能监控
    # ============================================================
    
    def get_performance_stats(self) -> dict:
        """获取性能统计"""
        return self._perf_monitor.get_summary()
    
    def print_performance_stats(self):
        """打印性能统计"""
        self._perf_monitor.print_summary()
    
    def reset_performance_stats(self):
        """重置性能统计"""
        self._perf_monitor.reset()
    
    # ============================================================
    #  启动方法
    # ============================================================
    
    def start(self, blocking: bool = True):
        """启动对话循环"""
        self.initialize()
        
        if blocking:
            asyncio.run(self.run_async())
        else:
            # 在后台线程运行事件循环
            import threading
            def run_in_thread():
                asyncio.run(self.run_async())
            thread = threading.Thread(target=run_in_thread, daemon=True)
            thread.start()
    
    async def stop(self):
        """停止对话（异步版本）"""
        log.info("[对话] 正在停止异步对话系统...")
        
        # 取消当前 turn
        await self.cancel_current_turn()
        
        # 停止音频设备
        if self._audio_output:
            self._audio_output.stop()
        
        if self._audio_input:
            self._audio_input.stop_listening()
        
        # 停止 ASR
        if self._asr and hasattr(self._asr, 'stop'):
            self._asr.stop()
        
        log.info("[对话] 异步对话系统已停止")
    
    def stop_sync(self):
        """停止对话（同步版本，用于从非异步上下文调用）"""
        self._running.clear()
        self._user_text_queue = None
        
        # 停止音频设备
        if self._audio_output:
            self._audio_output.stop()
        
        if self._audio_input:
            self._audio_input.stop_listening()
        
        # 停止 ASR
        if self._asr and hasattr(self._asr, 'stop'):
            self._asr.stop()
        
        log.info("[对话] 异步对话系统已停止（同步调用）")


# ============================================================
#  便捷启动函数
# ============================================================

def start_async_conversation(
    user_id: str = "default_user",
    blocking: bool = True
) -> AsyncConversationManager:
    """快速启动异步对话"""
    cfg = get_config_manager().config
    cfg.general.user_id = user_id
    manager = AsyncConversationManager(cfg)
    manager.start(blocking=blocking)
    return manager


if __name__ == "__main__":
    print("启动异步对话管理器...")
    start_async_conversation()
