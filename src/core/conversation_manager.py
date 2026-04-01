# -*- coding: utf-8 -*-
"""
对话管理器
整合 ASR + Agent + TTS 实现完整对话流程

使用方式:
    from core.conversation_manager import ConversationManager
    
    manager = ConversationManager()
    manager.start()  # 开始对话循环
"""

import sys
import time
import threading
import queue
import re
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np

# 添加路径
project_root = Path(__file__).parent.parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from core.audio_io import AudioInput, AudioOutput, AudioConfig
from core.vad import VADConfig
from core.log import log
from core.exit_signal import consume_exit_request
from core.emotion_classifier import EmotionClassifier
from core.ser_engine import SEREngine, SERResult


class ConversationState(Enum):
    """对话状态"""
    IDLE = "idle"                  # 空闲，等待用户说话
    LISTENING = "listening"        # 正在监听用户
    PROCESSING = "processing"      # 正在处理（ASR + Agent）
    SPEAKING = "speaking"          # AI 正在说话
    PAUSED = "paused"             # 暂停


@dataclass
class ConversationConfig:
    """对话配置"""
    # ASR 配置
    asr_model_dir: str = None      # ASR 模型目录（本地 FunASR）
    asr_provider: str = "funasr"   # "funasr" | "whisper"
    asr_device: str = "auto"       # "auto" | "cpu" | "cuda" | "cuda:0"
    whisper_api_base: str = None   # 远程 Whisper API（如 "https://api.openai.com/v1"）
    whisper_api_key: str = None    # API Key
    use_vad: bool = True           # 使用 VAD
    use_text_input: bool = False   # 使用终端文字输入（禁用ASR/麦克风）
    
    # TTS 配置
    tts_model_dir: str = None      # TTS 模型目录（本地模式）
    tts_remote_url: str = None     # TTS 服务地址（远程模式，如 "http://server:5001"）
    tts_spk_id: str = None         # 说话人 ID
    
    # Agent 配置
    user_id: str = "default_user"
    
    # 音频 / VAD 配置
    sample_rate: int = 16000
    silence_threshold: float = 0.01
    silence_duration: float = 0.6   # 静音多久认为说完
    vad_backend: str = "rms"        # "rms" | "silero"
    vad_preset: str = "balanced"    # "aggressive" | "balanced" | "conservative"
    
    # 交互配置
    interrupt_on_speak: bool = True
    auto_listen: bool = True

    # SER 配置（语音情绪识别）
    enable_ser: bool = True
    ser_model_id: str = None        # 默认使用 SEREngine.DEFAULT_MODEL_ID
    ser_device: str = "auto"        # "auto" | "cpu" | "cuda" | "cuda:0"
    ser_min_audio_sec: float = 0.8  # 太短的语音不做 SER（减少误判/开销）


class ConversationManager:
    """
    对话管理器
    
    核心功能:
    1. 监听用户语音 → ASR 识别
    2. 用户文本 → Agent 生成回复
    3. 回复文本 → TTS 合成播放
    4. 循环等待下一轮对话
    """
    
    def __init__(self, config: ConversationConfig = None):
        self.config = config or ConversationConfig()
        self.state = ConversationState.IDLE
        
        # 组件（延迟初始化）
        self._asr = None
        self._tts = None
        self._tts_mode = None  # "local" 或 "remote"
        self._agent = None
        self._audio_input = None
        self._audio_output = None
        
        # 线程控制
        self._running = False
        self._conversation_thread = None
        self._message_queue = queue.Queue()
        
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
        
        # 字幕服务
        self._subtitle_callback = None
        
        # 提醒管理器
        self._reminder_manager = None
    
    def _init_asr(self):
        """初始化 ASR（FunASR 本地或 Whisper 远程）"""
        if self._asr is not None:
            return
        
        if self.config.use_text_input:
            log.debug("[对话] 使用文字输入模式，跳过 ASR 初始化")
            self._asr = None
            return
        
        provider = (self.config.asr_provider or "funasr").lower()
        
        if provider == "whisper":
            try:
                from backend.asr.providers import WhisperRemoteProvider
                base = self.config.whisper_api_base or "https://api.openai.com/v1"
                key = self.config.whisper_api_key or ""
                self._asr = WhisperRemoteProvider(api_base=base, api_key=key)
                log.debug("[对话] ASR: Whisper 远程模式")
            except Exception as e:
                log.warn(f"Whisper ASR 初始化失败: {e}")
                self._asr = None
            return
        
        # FunASR 本地
        try:
            from backend.asr.providers import FunASRProvider
            
            model_dir = self.config.asr_model_dir
            if not model_dir:
                for p in [
                    project_root / "models" / "ASR" / "paraformer-zh-streaming",
                    Path("E:/Avalon/Chaldea/Liying/models/ASR/paraformer-zh-streaming"),
                ]:
                    if p.exists():
                        model_dir = str(p)
                        break
            
            vad_model = None
            if self.config.use_vad:
                for p in [
                    project_root / "models" / "ASR" / "fsmn-vad",
                    Path("E:/Avalon/Chaldea/Liying/models/ASR/fsmn-vad"),
                ]:
                    if p.exists():
                        vad_model = str(p)
                        break
                vad_model = vad_model or "fsmn-vad"
            
            if model_dir and Path(model_dir).exists():
                asr_device = self._resolve_asr_device(self.config.asr_device)
                self._asr = FunASRProvider(model_dir=model_dir, vad_model=vad_model, device=asr_device)
                log.debug(f"[对话] ASR: FunASR 本地模式 (device={asr_device})")
            else:
                log.warn(f"ASR 模型目录不存在: {model_dir}")
                self._asr = None
        except Exception as e:
            log.warn(f"ASR 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            self._asr = None

    def _resolve_asr_device(self, requested: str) -> str:
        """解析 ASR 设备：支持 auto 自动选择 CUDA/CPU。"""
        req = (requested or "auto").strip().lower()

        def _cuda_available() -> bool:
            try:
                import torch
                return bool(torch.cuda.is_available())
            except Exception:
                return False

        if req == "auto":
            return "cuda:0" if _cuda_available() else "cpu"

        if req == "cuda":
            req = "cuda:0"

        if req.startswith("cuda"):
            if _cuda_available():
                return req
            log.warn(f"ASR 指定设备 '{requested}' 不可用，已回退到 cpu")
            return "cpu"

        return "cpu"
    
    def _init_tts(self):
        """初始化 TTS（支持本地和远程模式）"""
        if self._tts is not None:
            return
        
        # 优先使用远程 TTS
        if self.config.tts_remote_url:
            try:
                from backend.tts.remote_client import RemoteTTSClient, RemoteTTSConfig
                
                remote_config = RemoteTTSConfig(
                    base_url=self.config.tts_remote_url,
                    spk_id=self.config.tts_spk_id,
                )
                client = RemoteTTSClient(remote_config)
                
                # 检查服务是否可用
                if client.health_check():
                    self._tts = client
                    self._tts_mode = "remote"
                    log.debug(f"[对话] TTS 远程服务初始化完成: {self.config.tts_remote_url}")
                    return
                else:
                    log.warn(f"TTS 远程服务不可用: {self.config.tts_remote_url}")
                    log.debug("尝试使用本地 TTS...")
            except Exception as e:
                log.warn(f"TTS 远程服务初始化失败: {e}")
                log.debug("尝试使用本地 TTS...")
        
        # 本地 TTS
        try:
            from backend.tts.engine import CosyvoiceRealTimeTTS
            
            # 查找模型目录
            model_dir = self.config.tts_model_dir
            if not model_dir:
                default_paths = [
                    project_root / "models" / "TTS" / "CosyVoice2-0.5B",
                    Path("E:/Avalon/Chaldea/Liying/models/TTS/CosyVoice2-0.5B"),
                ]
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
                log.info("将使用文本输出代替语音")
                self._tts = None
                self._tts_mode = None
        except Exception as e:
            log.warn(f"TTS 初始化失败: {e}")
            log.info("将使用文本输出代替语音")
            self._tts = None
            self._tts_mode = None
    
    def _init_agent(self):
        """初始化 Agent"""
        if self._agent is not None:
            return
        
        try:
            from backend.llm.agent import Agent
            
            self._agent = Agent(user_id=self.config.user_id)
            self._agent.start_chat()
            log.debug("[对话] Agent 初始化完成")
        except Exception as e:
            log.error(f"Agent 初始化失败: {e}")
            raise
    
    def _init_reminder(self):
        """初始化提醒管理器"""
        try:
            from backend.llm.tools.reminder_tool import ReminderManager
            
            self._reminder_manager = ReminderManager.get_instance()
            self._reminder_manager.initialize()
            self._reminder_manager.set_on_remind(self._on_reminder_triggered)
            self._reminder_manager.start()
            log.debug("[对话] 提醒管理器初始化完成")
        except Exception as e:
            log.warn(f"提醒管理器初始化失败（非致命）: {e}")
            self._reminder_manager = None
    
    def _on_reminder_triggered(self, reminder: dict):
        """
        提醒到期时的回调
        通过字幕通知用户 + TTS 播报（如果可用）
        """
        content = reminder.get("content", "提醒时间到了")
        notify_text = f"⏰ 提醒：{content}"
        
        log.info(f"[提醒] 触发: {content}")
        print(f"\n{notify_text}")
        
        # 发送字幕到 Live2D 气泡框
        self._send_subtitle(notify_text, is_final=True, emotion="happy")
        
        # 如果有 AI 回复回调也通知
        if self._on_ai_text:
            self._on_ai_text(notify_text)
        
        # TTS 播报
        if self._tts and self._audio_output:
            try:
                self._speak(f"提醒时间到了，{content}")
            except Exception as e:
                log.warn(f"提醒 TTS 播报失败: {e}")
    
    def _init_audio(self):
        """初始化音频设备（chunk_size 从 ASR 获取，VAD 可配置）"""
        self._init_asr()
        
        chunk_size = 5760  # 默认 360ms
        if self._asr and hasattr(self._asr, "get_chunk_stride"):
            chunk_size = self._asr.get_chunk_stride()
            log.debug(f"[AudioIO] chunk_stride: {chunk_size} ({chunk_size / self.config.sample_rate * 1000:.0f}ms)")
        
        vad_config = VADConfig.preset(self.config.vad_preset)
        vad_config.backend = self.config.vad_backend
        vad_config.silence_duration = self.config.silence_duration
        # 提高端点稳定性，减少句尾截断与误触发
        vad_config.min_speech_chunks = max(2, vad_config.min_speech_chunks)
        vad_config.hangover_chunks = max(2, vad_config.hangover_chunks)
        vad_config.pre_buffer_chunks = max(4, vad_config.pre_buffer_chunks)
        
        audio_config = AudioConfig(
            sample_rate=self.config.sample_rate,
            dtype="float32",
            chunk_size=chunk_size,
            vad_config=vad_config,
            vad_backend=self.config.vad_backend,
        )
        self._audio_input = AudioInput(audio_config)
        self._audio_output = AudioOutput()
        log.debug("[对话] 音频设备初始化完成")

    def _init_ser(self):
        """初始化 SER（懒加载 pipeline；失败不影响主流程）"""
        if not self.config.enable_ser:
            self._ser = None
            return
        if self._ser is not None:
            return
        try:
            self._ser = SEREngine(
                model_id=self.config.ser_model_id,
                device=self.config.ser_device,
            )
            log.debug("[对话] SER 初始化完成（懒加载模型）")
        except Exception as e:
            log.warn(f"SER 初始化失败（将跳过语音情绪识别）: {e}")
            self._ser = None

    @staticmethod
    def _emotion9_to_cn(e: str) -> str:
        m = {
            "neutral": "中性",
            "joy": "愉快",
            "anger": "愤怒",
            "sadness": "悲伤",
            "surprise": "惊讶",
            "shy": "害羞",
            "think": "思考",
            "fear": "害怕",
            "cry": "想哭",
        }
        return m.get(e, e)
    
    def initialize(self):
        """初始化所有组件"""
        log.debug("[对话] 正在初始化对话系统...")
        # 注意：_init_audio 内部会先调用 _init_asr，用于获取 chunk_stride
        self._init_audio()
        self._init_tts()
        self._init_agent()
        self._init_reminder()
        self._init_ser()
        log.info("对话系统初始化完成")
    
    def set_callbacks(
        self,
        on_state_change: Callable[[ConversationState], None] = None,
        on_user_text: Callable[[str], None] = None,
        on_ai_text: Callable[[str], None] = None,
        on_subtitle: Callable[[str, bool], None] = None,
        on_audio_rms: Callable[[float], None] = None,
        on_viseme: Callable[[float, float], None] = None,
        on_exit_requested: Callable[[str], None] = None,
    ):
        """
        设置回调函数
        
        Args:
            on_state_change: 状态变化回调
            on_user_text: 用户文本回调
            on_ai_text: AI 回复回调
            on_subtitle: 字幕回调 (text, is_final, emotion)
            on_audio_rms: 音频 RMS 回调 (rms_value) — 驱动嘴型同步
            on_viseme: Viseme 回调 (openY, form) — Rhubarb 口型同步
            on_exit_requested: 退出请求回调 (reason)
        """
        self._on_state_change = on_state_change
        self._on_user_text = on_user_text
        self._on_ai_text = on_ai_text
        self._on_subtitle = on_subtitle
        self._on_audio_rms = on_audio_rms
        self._on_viseme = on_viseme
        self._on_exit_requested = on_exit_requested
    
    def _set_state(self, state: ConversationState):
        """设置状态"""
        old_state = self.state
        self.state = state
        log.debug(f"[对话] 状态: {old_state.value} → {state.value}")
        if self._on_state_change:
            self._on_state_change(state)
    
    def _send_subtitle(self, text: str, is_final: bool = False, emotion: str = "neutral"):
        """发送字幕（带情绪标签）"""
        if self._on_subtitle:
            self._on_subtitle(text, is_final, emotion)
    
    def start(self, blocking: bool = True):
        """
        启动对话循环
        
        Args:
            blocking: 是否阻塞当前线程
        """
        if self._running:
            return
        
        # 初始化组件
        self.initialize()
        
        self._running = True
        
        if blocking:
            self._conversation_loop()
        else:
            self._conversation_thread = threading.Thread(
                target=self._conversation_loop,
                daemon=True
            )
            self._conversation_thread.start()
    
    def stop(self):
        """停止对话"""
        self._running = False
        
        if self._audio_input:
            self._audio_input.stop_listening()
        if self._audio_output:
            self._audio_output.stop()
        
        if self._reminder_manager:
            self._reminder_manager.stop()
        
        if self._agent:
            self._agent.end_chat()
        
        log.debug("对话已停止")
    
    def _conversation_loop(self):
        """对话主循环"""
        log.info("\n对话系统已启动，说话开始对话，或输入 'quit' 退出\n")
        
        while self._running:
            try:
                # 1. 等待并获取用户输入
                self._set_state(ConversationState.LISTENING)
                t0_input = time.perf_counter()
                user_text = self._listen_and_recognize()
                elapsed_input = time.perf_counter() - t0_input
                if user_text:
                    log.debug(f"[耗时] 输入/ASR: {elapsed_input:.2f}s")
                if not user_text:
                    continue
                
                if user_text.lower() in ['quit', 'exit', '退出', '结束']:
                    log.debug("收到退出指令")
                    break
                
                print(f"\n👤 用户: {user_text}")
                if self._on_user_text:
                    self._on_user_text(user_text)
                
                # 2. Agent 生成回复
                self._set_state(ConversationState.PROCESSING)
                t0_agent = time.perf_counter()
                ai_response = self._generate_response(user_text)
                elapsed_agent = time.perf_counter() - t0_agent
                log.debug(f"[耗时] Agent: {elapsed_agent:.2f}s")
                
                if not ai_response:
                    continue
                
                print(f"🤖 AI: {ai_response}")
                if self._on_ai_text:
                    self._on_ai_text(ai_response)
                
                # 3. TTS 播放
                self._set_state(ConversationState.SPEAKING)
                t0_tts = time.perf_counter()
                # 说话时暂停麦克风，避免回声/串音污染下一轮 ASR 队列
                try:
                    if self._audio_input:
                        self._audio_input.stop_listening()
                except Exception:
                    pass
                self._speak(ai_response)
                try:
                    if self._audio_input and self.config.auto_listen:
                        self._audio_input.start_listening()
                except Exception:
                    pass
                log.debug(f"[耗时] TTS+播放 总: {time.perf_counter() - t0_tts:.2f}s")

                # Agent 工具请求退出：等本轮 TTS 播完后再退出
                exit_reason = consume_exit_request()
                if exit_reason is not None:
                    log.info(f"收到退出请求，准备退出程序: {exit_reason}")
                    if self._on_exit_requested:
                        try:
                            self._on_exit_requested(exit_reason)
                        except Exception as e:
                            log.warn(f"退出回调执行失败: {e}")
                    break
                
                # 4. 回到监听状态
                self._set_state(ConversationState.IDLE)
                
            except KeyboardInterrupt:
                print("\n用户中断")
                break
            except Exception as e:
                log.error(f"对话错误: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)
        
        self.stop()
    
    def _listen_and_recognize(self) -> Optional[str]:
        """监听并识别语音"""
        # 有 ASR 引擎即走麦克风（模型在首次 start_stream 时延迟加载，不要求 is_model_loaded）
        if self._asr:
            try:
                return self._listen_with_asr()
            except Exception as e:
                log.warn(f"ASR 识别异常，本次使用文本输入: {e}")
                return self._listen_with_text()
        return self._listen_with_text()

    def _merge_streaming_results(self, parts: list) -> str:
        """
        合并流式识别结果，去重
        FunASR 流式返回累积结果（新=旧+增量），直接 append 会重复，取最长作为累积文本
        """
        if not parts:
            return ""
        merged = (parts[0] or "").strip()
        for p in parts[1:]:
            if not p:
                continue
            p = p.strip()
            if not p:
                continue
            if p.startswith(merged):
                merged = p
            elif merged.endswith(p[:min(len(p), len(merged))]):
                for i in range(min(len(p), len(merged)), 0, -1):
                    if merged.endswith(p[:i]):
                        merged = merged + p[i:]
                        break
                else:
                    merged = merged + p
            else:
                merged = merged + p
        return merged.strip()

    def _collapse_repeated_asr_text(self, text: str) -> str:
        """
        折叠 ASR 误重复的整句文本。

        仅处理“同一短句完整重复 2~4 次”的情况，避免影响正常表达。
        例如："喂你好喂你好喂你好" -> "喂你好"
        """
        if not text:
            return ""

        s = text.strip()
        if len(s) < 4:
            return s

        # 仅在整句完全重复时折叠（2~4 次），并限制句长避免误伤长文本
        m = re.fullmatch(r"(.{2,20}?)\1{1,3}", s)
        if not m:
            return s

        unit = m.group(1)
        # 跳过单字符重复（如“哈哈哈”），尽量降低误判
        if len(set(unit)) == 1:
            return s

        return unit

    def _listen_with_asr(self) -> Optional[str]:
        """
        使用 ASR 监听麦克风
        
        - 本地 FunASR：流式中间结果用于实时字幕，end_stream 为最终结果
        - 远程 Whisper：无流式，录音结束后整段发送
        - 麦克风始终本地采集
        """
        log.info("🎤 请说话...")
        
        streaming_parts = []
        full_audio_ref = [None]
        supports_streaming = getattr(self._asr, "supports_streaming", False)

        def on_speech_start():
            log.debug("检测到语音...")

        def on_chunk(chunk):
            if self._asr:
                result = self._asr.feed_audio(chunk)
                if result and supports_streaming:
                    streaming_parts.append(result)
                    merged = self._merge_streaming_results(streaming_parts)
                    log.debug(f"[ASR] 中间: '{merged}'")

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
        merged_stream = self._merge_streaming_results(streaming_parts)
        
        if supports_streaming and not final:
            final = merged_stream
        elif supports_streaming and merged_stream and len(merged_stream) > len(final) + 1:
            # 某些场景 end_stream 仅返回尾字，优先采用更完整的流式合并结果
            final = merged_stream
        
        if full_audio is not None and len(full_audio) > 0:
            duration_sec = len(full_audio) / self.config.sample_rate
            # 仅在结果为空或过短时做离线兜底，兼顾准确率与时延
            if duration_sec > 0.7 and (not final or len(final) <= 1):
                try:
                    offline = self._asr.recognize_audio(full_audio, self.config.sample_rate)
                    if offline and len(offline) >= len(final):
                        final = offline.strip()
                except Exception as e:
                    log.warn(f"离线识别失败: {e}")

            # SER：对用户语音做情绪识别（不阻塞主流程太久；失败则忽略）
            if self.config.enable_ser and duration_sec >= (self.config.ser_min_audio_sec or 0.8):
                try:
                    self._init_ser()
                    if self._ser is not None:
                        t0_ser = time.perf_counter()
                        r: SERResult = self._ser.predict(full_audio, sample_rate=self.config.sample_rate)
                        self._current_user_emotion = r.emotion9
                        log.debug(f"[耗时] SER: {time.perf_counter() - t0_ser:.2f}s, emo={r.emotion9}, score={r.score:.2f}")
                except Exception as e:
                    log.debug(f"SER 推断失败（忽略）: {e}")
        
        final = self._collapse_repeated_asr_text(final)

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
    
    # ============================================================
    #  情绪解析
    # ============================================================
    _EMOTION_PATTERN = re.compile(r'\[(joy|anger|sadness|surprise|neutral|shy|think|fear|cry)\]', re.IGNORECASE)
    _VALID_EMOTIONS = {"neutral", "joy", "anger", "sadness", "surprise", "shy", "think", "fear", "cry"}

    def _parse_emotion(self, text: str) -> tuple:
        """从 AI 回复中提取情绪标签，返回 (clean_text, emotion)。

        优先级：
        1. 显式标签（如 [joy]）
        2. 规则情绪分类兜底
        """
        emotions_found = self._EMOTION_PATTERN.findall(text)
        emotion = "neutral"
        for e in emotions_found:
            if e.lower() in self._VALID_EMOTIONS:
                emotion = e.lower()
                break
        clean_text = self._EMOTION_PATTERN.sub("", text).strip()
        # 清除多余空格
        clean_text = re.sub(r'  +', ' ', clean_text)

        # 无显式标签时进行轻量规则推断
        if emotion == "neutral" and clean_text:
            inferred = self._emotion_classifier.classify(clean_text)
            if inferred.emotion in self._VALID_EMOTIONS:
                emotion = inferred.emotion

        return (clean_text or text.strip(), emotion)

    def _generate_response(self, user_text: str) -> Optional[str]:
        """生成 AI 回复（带情绪解析）"""
        if not self._agent:
            return "抱歉，AI 服务未初始化"
        
        try:
            # 将用户语音情绪作为上下文提示（尽量不污染语义检索：只加一行简短信息）
            user_input = user_text
            ue = (self._current_user_emotion or "neutral").strip().lower()
            if ue and ue != "neutral":
                user_input = f"（用户当前情绪：{self._emotion9_to_cn(ue)}）{user_text}"

            # 流式获取回复；字幕节流
            response_parts = []
            last_sent_len = 0
            SUBTITLE_CHUNK = 6  # WebSocket 更快，可以更频繁更新

            for chunk in self._agent.chat(user_input, stream=True):
                response_parts.append(chunk)
                current = "".join(response_parts)
                if len(current) - last_sent_len >= SUBTITLE_CHUNK:
                    # 流式中间结果：清除情绪标签后发送
                    clean, _ = self._parse_emotion(current)
                    self._send_subtitle(clean, is_final=False)
                    last_sent_len = len(current)

            full_response = "".join(response_parts)
            
            # 解析情绪标签
            clean_text, emotion = self._parse_emotion(full_response)
            self._current_emotion = emotion
            
            # 发送最终字幕（带情绪）
            self._send_subtitle(clean_text, is_final=True, emotion=emotion)

            return clean_text  # 返回清洗后的文本给 TTS
            
        except Exception as e:
            log.error(f"Agent 错误: {e}")
            return f"抱歉，处理时出错了: {e}"
    
    def _text_for_tts(self, text: str) -> str:
        """清洗 AI 回复，便于 TTS 朗读：去 Markdown、颜文字、多余换行"""
        if not text:
            return ""
        s = text.strip()
        # 去掉 **粗体**
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        # 去掉 *斜体*（单星号，避免误伤乘号）
        s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"\1", s)
        # 列表行 "- xxx" 或 "- **xxx**：" 改为 "xxx，"
        s = re.sub(r"^\s*[-*]\s*\**(.+?)\**[：:]\s*", r"\1，", s, flags=re.MULTILINE)
        s = re.sub(r"^\s*[-*]\s+(.+)$", r"\1，", s, flags=re.MULTILINE)
        # 常见颜文字 / 括号表情
        s = re.sub(r"\([^()]*[•◍ᴗ￣▽ω´`～～\s]+[^()]*\)", "", s)
        s = re.sub(r"（[^（）]*[•◍ᴗ￣▽ω´`～～\s]+[^（）]*）", "", s)
        # 多余换行合并为一句内的停顿
        s = re.sub(r"\n\s*\n\s*", "。", s)
        s = re.sub(r"\n\s*", "，", s)
        s = re.sub(r"[,，]+", "，", s)
        return s.strip() or text.strip()

    def _speak(self, text: str):
        """TTS 播放（流式：边合成边播放，同时发送 RMS 驱动嘴型）"""
        if not text:
            return
        text = self._text_for_tts(text)

        if self._tts:
            try:
                # 使用流式合成 + 边生成边播放
                first_chunk = True
                t_tts_start = time.perf_counter()
                log.debug("正在合成语音...")
                for chunk_data in self._tts.generate_audio_streaming(
                    text, use_clone=True, max_workers=2
                ):
                    # 兼容新版（含 visemes）和旧版（3元组）
                    if len(chunk_data) == 4:
                        audio, seg_idx, total, visemes = chunk_data
                    else:
                        audio, seg_idx, total = chunk_data
                        visemes = None

                    if first_chunk:
                        t_first_chunk = time.perf_counter() - t_tts_start
                        log.debug(f"开始播放... [耗时] TTS 首包: {t_first_chunk:.2f}s")
                        first_chunk = False
                    
                    # 启动嘴型同步线程（与播放同步）
                    if visemes and self._on_viseme:
                        # 优先使用 Rhubarb viseme 数据驱动口型
                        lip_thread = threading.Thread(
                            target=self._send_visemes_for_chunk,
                            args=(visemes, audio, self._tts.sample_rate),
                            daemon=True,
                            name="Viseme-Sender",
                        )
                        lip_thread.start()
                    elif self._on_audio_rms:
                        # Fallback: 用 RMS 驱动嘴型
                        rms_thread = threading.Thread(
                            target=self._send_rms_for_chunk,
                            args=(audio, self._tts.sample_rate),
                            daemon=True,
                            name="RMS-Sender",
                        )
                        rms_thread.start()
                    
                    # 直接播放当前段（阻塞直到播放完）
                    self._audio_output.play_array(
                        audio, 
                        self._tts.sample_rate, 
                        blocking=True
                    )
                
                # 播放结束，重置嘴型
                if self._on_viseme:
                    self._on_viseme(0.0, 0.0)
                if self._on_audio_rms:
                    self._on_audio_rms(0.0)
                
                if first_chunk:
                    # 没有生成任何音频
                    log.debug("TTS 未生成音频")
                return
                    
            except Exception as e:
                log.error(f"TTS 错误: {e}")
                import traceback
                traceback.print_exc()
        
        # TTS 不可用，只显示文本
        log.debug("TTS 不可用，文本输出")
        time.sleep(len(text) * 0.05)  # 模拟说话时间

    def _send_rms_for_chunk(self, audio, sample_rate: int):
        """在音频播放期间按 ~20fps 发送 RMS 值，驱动嘴型同步"""
        try:
            window_ms = 50  # 50ms 窗口
            window_samples = max(1, int(sample_rate * window_ms / 1000))
            
            audio_float = audio.astype(np.float32)
            # 归一化到 [-1, 1]
            max_val = np.max(np.abs(audio_float))
            if max_val > 1.0:
                audio_float = audio_float / 32768.0
            
            for i in range(0, len(audio_float), window_samples):
                window = audio_float[i:i + window_samples]
                rms = float(np.sqrt(np.mean(window ** 2)))
                if self._on_audio_rms:
                    self._on_audio_rms(rms)
                time.sleep(window_ms / 1000.0)
        except Exception:
            pass

    # Rhubarb 口型映射: shape → (openY, form)
    # A=静息/小口  B=轻合唇音  C=较开口  D=大开口  E=圆嘴音  F=窄口音  G=轻开  H=微开
    VISEME_SHAPE_MAP = {
        'X': (0.00, 0.00),   # 闭嘴（静音）
        'A': (0.05, 0.00),   # 口型很小，中性
        'B': (0.25, 0.60),   # 双唇轻合（b/m/p）— 偏笑口形
        'C': (0.50, 0.20),   # 中等开口（e/辅音）
        'D': (0.85, 0.40),   # 大张口（a）
        'E': (0.55, -0.40),  # 圆嘴（o）— form 负值
        'F': (0.35, -0.70),  # 窄嘴（u/w）— form 更负
        'G': (0.20, 0.30),   # 轻开口（辅音）
        'H': (0.40, 0.10),   # 中等开口（l）
    }

    def _send_visemes_for_chunk(self, visemes: list, audio, sample_rate: int):
        """按 Rhubarb 时间线发送 viseme 口型数据，精确同步播放"""
        try:
            if not visemes:
                return
            audio_duration = len(audio) / max(1, sample_rate)
            t0 = time.perf_counter()
            interval = 1.0 / 30  # 30fps 推送率

            # 将 visemes 按时间展平为帧序列
            cue_idx = 0
            current_shape = 'X'
            elapsed = 0.0
            while elapsed < audio_duration:
                # 推进到当前时刻对应的 cue
                while cue_idx < len(visemes) - 1:
                    next_start = visemes[cue_idx + 1].get('start', 999)
                    if elapsed >= next_start:
                        cue_idx += 1
                    else:
                        break
                current_shape = visemes[cue_idx].get('value', 'X')
                openY, form = self.VISEME_SHAPE_MAP.get(current_shape, (0.0, 0.0))

                if self._on_viseme:
                    self._on_viseme(openY, form)

                time.sleep(interval)
                elapsed = time.perf_counter() - t0

            # 结束时发送闭嘴
            if self._on_viseme:
                self._on_viseme(0.0, 0.0)
        except Exception:
            pass
    
    # === 手动触发方法（供外部调用）===
    
    def send_text(self, text: str):
        """
        手动发送文本（跳过 ASR）
        
        用于 GUI 文本输入或测试
        """
        self._message_queue.put(("text", text))
    
    def trigger_listen(self):
        """手动触发监听"""
        self._message_queue.put(("listen", None))
    
    def interrupt(self):
        """打断当前操作"""
        if self.state == ConversationState.SPEAKING:
            self._audio_output.stop()
        self._set_state(ConversationState.IDLE)


# === 便捷启动函数 ===

def start_conversation(
    user_id: str = "default_user",
    blocking: bool = True
) -> ConversationManager:
    """
    快速启动对话
    
    Args:
        user_id: 用户 ID
        blocking: 是否阻塞
        
    Returns:
        ConversationManager 实例
    """
    config = ConversationConfig(user_id=user_id)
    manager = ConversationManager(config)
    manager.start(blocking=blocking)
    return manager


if __name__ == "__main__":
    # 测试运行
    print("启动对话管理器...")
    start_conversation()
