# -*- coding: utf-8 -*-
"""
ASR 处理器（Mixin）

从 conversation_manager.py 拆分而来，包含所有 ASR 相关的初始化、监听、
流式合并、SV 门控、SER 情绪识别、说话人识别、标点恢复等方法。

作为 mixin 被 ConversationManager 继承，通过 self 访问管理器的属性。
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Callable

import numpy as np

from core.log import log
from core.ser_engine import SEREngine, SERResult
from core.punc_engine import PUNCEngine
from core.sv_engine import SVEngine, SVResult

if TYPE_CHECKING:
    from core.conversation.state import ConversationConfig

logger = logging.getLogger(__name__)

# 项目根目录（与 conversation_manager_async.py 保持一致）
project_root = Path(__file__).parent.parent.parent


class ASRHandler:
    """ASR 处理 Mixin —— 提供语音识别、说话人验证、情绪识别等能力。

    被 ConversationManager 继承。子类必须提供以下属性：
      config, _asr, _audio_input, _ser, _punc, _sv, _diarization,
      _current_user_id, _current_user_emotion, _agent,
      _on_speaker_change_callback, _on_subtitle
    """

    # ------------------------------------------------------------------
    # 情绪标签正则
    # ------------------------------------------------------------------
    _EMOTION_PATTERN = re.compile(
        r'\[(joy|anger|sadness|surprise|neutral|shy|think|fear|cry)\]',
        re.IGNORECASE,
    )
    _VALID_EMOTIONS = {
        "neutral", "joy", "anger", "sadness", "surprise",
        "shy", "think", "fear", "cry",
    }

    # ------------------------------------------------------------------
    # ASR 初始化
    # ------------------------------------------------------------------

    def _get_asr_stream_profile(self) -> dict:  # noqa: D401
        """根据配置返回 ASR 流式参数档位。"""
        profile = (self.config.asr_stream_profile or "balanced").strip().lower()
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
                try:
                    from core.config_manager import get_config_manager
                    cfg = get_config_manager().config
                    if cfg.asr.model_dir:
                        model_dir = cfg.asr.model_dir
                except Exception:
                    logger.debug("Failed to load ASR model dir from ConfigManager")
                if not model_dir:
                    for p in [
                        project_root / "models" / "ASR" / "paraformer-zh-streaming",
                    ]:
                        if p.exists():
                            model_dir = str(p)
                            break

            vad_model = None
            if self.config.use_vad:
                try:
                    from core.config_manager import get_config_manager
                    cfg = get_config_manager().config
                    if cfg.asr.vad_model_dir:
                        vad_model = cfg.asr.vad_model_dir
                except Exception:
                    logger.debug("Failed to load VAD model dir from ConfigManager")
                if not vad_model:
                    for p in [
                        project_root / "models" / "ASR" / "fsmn-vad",
                    ]:
                        if p.exists():
                            vad_model = str(p)
                            break
                vad_model = vad_model or "fsmn-vad"

            if model_dir and Path(model_dir).exists():
                asr_device = self._resolve_asr_device(self.config.asr_device)
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
                    f"chunk={stream_cfg.get('chunk_size')}, "
                    f"enc_lb={stream_cfg.get('encoder_chunk_look_back')}, "
                    f"dec_lb={stream_cfg.get('decoder_chunk_look_back')})"
                )
            else:
                log.warn(f"ASR 模型目录不存在: {model_dir}")
                self._asr = None
        except Exception as e:
            log.warn(f"ASR 初始化失败: {e}")
            import traceback
            log.error(traceback.format_exc())
            self._asr = None

    def _resolve_asr_device(self, requested: str) -> str:
        """解析 ASR 设备：支持 auto 自动选择 CUDA/CPU。"""
        req = (requested or "auto").strip().lower()

        def _cuda_available() -> bool:
            try:
                import torch
                return bool(torch.cuda.is_available())
            except Exception:
                logger.debug("torch.cuda.is_available() check failed, falling back to CPU")
                return False

        def _cuda_count() -> int:
            try:
                import torch
                return int(torch.cuda.device_count())
            except Exception:
                logger.debug("torch.cuda.device_count() check failed, returning 0")
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
                log.warn(
                    f"ASR 指定设备 '{requested}' 越界"
                    f"（GPU 数量={count}），已回退到 {fallback}"
                )
                return fallback
            if req == "cuda":
                return "cuda:0"
            log.warn(f"ASR 指定设备 '{requested}' 不可用，已回退到 cpu")
            return "cpu"

        return "cpu"

    # ------------------------------------------------------------------
    # SER / PUNC / SV 初始化
    # ------------------------------------------------------------------

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

    def _init_punc(self):
        """初始化 PUNC（失败自动回退到启发式标点恢复）。"""
        if not self.config.enable_punc:
            self._punc = None
            return
        if self._punc is not None:
            return
        try:
            self._punc = PUNCEngine(
                model_id=self.config.punc_model_id,
                device=self.config.punc_device,
            )
            log.debug("[对话] PUNC 初始化完成（懒加载模型）")
        except Exception as e:
            log.warn(f"PUNC 初始化失败（将使用启发式恢复）: {e}")
            self._punc = None

    def _init_sv(self):
        """初始化 SV（说话人验证），失败不阻塞主流程。"""
        if not self.config.enable_sv:
            self._sv = None
            return
        if self._sv is not None:
            return
        try:
            self._sv = SVEngine(
                model_id=self.config.sv_model_id,
                device=self.config.sv_device,
                threshold=self.config.sv_threshold,
            )
            ref = (self.config.sv_enroll_audio or "").strip()
            if ref:
                p = Path(ref)
                if p.exists():
                    self._sv.enroll_file(p)
                    log.debug(f"[对话] SV 已加载参考说话人: {p}")
                else:
                    log.warn(f"SV 参考音频不存在，将以 fail-open 模式运行: {p}")
            else:
                log.debug("[对话] SV 未配置参考音频，默认 fail-open")
            log.debug("[对话] SV 初始化完成（懒加载模型）")
        except Exception as e:
            log.warn(f"SV 初始化失败（将跳过说话人门控）: {e}")
            self._sv = None

    # ------------------------------------------------------------------
    # 标点恢复 & SV 门控
    # ------------------------------------------------------------------

    def _apply_punc(self, text: str) -> str:
        """对最终 ASR 文本进行标点恢复。"""
        if not text:
            return ""
        if not self.config.enable_punc:
            return text
        self._init_punc()
        if self._punc is None:
            return text
        try:
            r = self._punc.restore(text)
            if r.text:
                log.debug(f"[ASR] PUNC: used_model={r.used_model}, reason={r.reason}")
                return r.text
            return text
        except Exception as e:
            log.warn(f"PUNC 处理失败，保留原文本: {e}")
            return text

    def _sv_accept(self, full_audio: np.ndarray, duration_sec: float) -> bool:
        """SV 门控：判断当前语音是否由目标说话人发出。"""
        if not self.config.enable_sv:
            return True
        if full_audio is None or len(full_audio) == 0:
            return True
        if duration_sec < (self.config.sv_min_audio_sec or 0.8):
            return True

        self._init_sv()
        if self._sv is None:
            return True

        try:
            r: SVResult = self._sv.verify(
                full_audio, sample_rate=self.config.sample_rate,
            )
            log.debug(
                f"[ASR] SV: accept={r.accepted}, score={r.score:.3f}, "
                f"threshold={r.threshold:.3f}, reason={r.reason}"
            )
            if r.accepted:
                return True
            policy = (self.config.sv_reject_policy or "drop").strip().lower()
            return policy != "drop"
        except Exception as e:
            log.warn(f"SV 校验失败，按 fail-open 放行: {e}")
            return True

    # ------------------------------------------------------------------
    # 多说话人识别（Diarization）
    # ------------------------------------------------------------------

    def _init_diarization(self):
        """初始化说话人识别引擎（懒加载）"""
        if not self.config.enable_diarization:
            self._diarization = None
            return

        if self._diarization is not None:
            return

        try:
            from src.core.diarization_engine import DiarizationEngine
            from src.core.voiceprint_database import VoiceprintDatabase

            storage_path = Path(
                self.config.diarization_storage_path
                or (project_root / "data" / "voiceprints")
            )

            voiceprint_db = VoiceprintDatabase(storage_path)

            if len(voiceprint_db.list_all()) == 0:
                log.warn("未注册任何说话人，多说话人识别已禁用")
                self._diarization = None
                return

            self._diarization = DiarizationEngine(
                sv_engine=self._sv or SVEngine(),
                voiceprint_db=voiceprint_db,
                threshold=self.config.diarization_threshold,
                min_audio_sec=self.config.diarization_min_audio_sec,
                device=self.config.diarization_device,
                timeout_ms=self.config.diarization_timeout_ms,
                max_failures=3,
            )

            if self.config.notify_speaker_change:
                self._diarization.set_notification_callback(
                    self._notify_speaker_change,
                )

            log.debug("[对话] 多说话人识别初始化完成")
        except Exception as e:
            log.warn(f"多说话人识别初始化失败（回退到单用户模式）: {e}")
            self._diarization = None

    def _identify_speaker(self, audio: np.ndarray) -> str:
        """识别说话人，返回 user_id。"""
        if not self.config.enable_diarization or self._diarization is None:
            return self.config.user_id

        try:
            result = self._diarization.identify(audio, self.config.sample_rate)

            if result.speaker_id == "unknown":
                log.debug(
                    f"[说话人] 未识别: score={result.score:.3f}, "
                    f"reason={result.reason}"
                )
                return self.config.user_id

            user_id = self._speaker_id_to_user_id(result.speaker_id)

            if user_id != self._current_user_id:
                log.info(
                    f"[说话人] 切换: {self._current_user_id} → {user_id} "
                    f"(score={result.score:.3f})"
                )
                self._on_speaker_change(user_id, result)

            return user_id
        except Exception as e:
            log.warn(f"说话人识别失败，使用默认用户: {e}")
            return self.config.user_id

    def _speaker_id_to_user_id(self, speaker_id: str) -> str:
        """将 speaker_id 映射到 user_id"""
        return speaker_id

    def _on_speaker_change(self, new_user_id: str, result):
        """说话人切换回调"""
        if self._agent and self._current_user_id:
            try:
                if hasattr(self._agent, 'save_context'):
                    self._agent.save_context(self._current_user_id)
            except Exception as e:
                log.warn(f"保存用户上下文失败: {e}")

        self._current_user_id = new_user_id

        if self._agent:
            try:
                if hasattr(self._agent, 'load_context'):
                    self._agent.load_context(new_user_id)
                if hasattr(self._agent, 'user_id'):
                    self._agent.user_id = new_user_id
            except Exception as e:
                log.warn(f"加载用户上下文失败: {e}")

        if self._on_speaker_change_callback:
            try:
                self._on_speaker_change_callback(new_user_id, result)
            except Exception as e:
                log.warn(f"说话人切换通知失败: {e}")

    def _notify_speaker_change(self, message: str):
        """用户通知回调（用于 DiarizationEngine 的错误通知）"""
        log.info(f"[说话人识别] {message}")

    def set_speaker_change_callback(self, callback: Callable):
        """设置说话人切换回调"""
        self._on_speaker_change_callback = callback

    # ------------------------------------------------------------------
    # 情绪映射
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 流式文本合并
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_streaming_pair(base: str, incoming: str) -> str:
        """合并两段流式文本，优先保留更完整且不重复的结果。"""
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
        """合并流式识别结果，去重"""
        merged = ""
        for p in parts or []:
            merged = self._merge_streaming_pair(merged, p)
        return merged

    @staticmethod
    def _should_run_offline_fallback(audio: np.ndarray, duration_sec: float) -> bool:
        """判定是否值得做离线兜底识别。"""
        if audio is None or len(audio) == 0:
            return False
        if duration_sec < 0.35:
            return False
        try:
            a = np.asarray(audio, dtype=np.float32)
            if a.size == 0:
                return False
            rms = float(np.sqrt(np.mean(a ** 2)))
            return rms >= 0.002
        except Exception:
            logger.debug("Audio energy estimation failed, allowing offline fallback")
            return True

    def _collapse_repeated_asr_text(self, text: str) -> str:
        """折叠 ASR 误重复的整句文本。"""
        if not text:
            return ""

        s = text.strip()
        if len(s) < 4:
            return s

        m = re.fullmatch(
            r"(.{2,20}?)(?:[\s，,。.!！？?、]*)\1(?:[\s，,。.!！？?、]*\1){0,2}",
            s,
        )
        if not m:
            return s

        unit = m.group(1)
        if len(set(unit)) == 1:
            return s

        return unit

    # ------------------------------------------------------------------
    # ASR 监听
    # ------------------------------------------------------------------

    def _listen_and_recognize(self) -> Optional[str]:
        """监听并识别语音"""
        if self._asr:
            try:
                return self._listen_with_asr()
            except Exception as e:
                log.warn(f"ASR 识别异常，本次使用文本输入: {e}")
                return self._listen_with_text()
        return self._listen_with_text()

    def _listen_with_asr(self) -> Optional[str]:
        """使用 ASR 监听麦克风"""
        log.info("请说话...")

        streaming_parts = []
        merged_stream_ref = [""]
        last_partial_ref = [""]
        full_audio_ref = [None]
        supports_streaming = getattr(self._asr, "supports_streaming", False)

        def on_speech_start():
            log.debug("检测到语音...")

        def on_chunk(chunk):
            if self._asr:
                result = self._asr.feed_audio(chunk)
                if result and supports_streaming:
                    part = result.strip()
                    if part and part != last_partial_ref[0]:
                        last_partial_ref[0] = part
                        streaming_parts.append(part)
                        merged_stream_ref[0] = self._merge_streaming_pair(
                            merged_stream_ref[0], part,
                        )
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
        merged_stream = (
            merged_stream_ref[0]
            or self._merge_streaming_results(streaming_parts)
        )

        if supports_streaming and not final:
            final = merged_stream
        elif (
            supports_streaming
            and merged_stream
            and len(merged_stream) > len(final) + 1
            and final in merged_stream
        ):
            final = merged_stream

        if full_audio is not None and len(full_audio) > 0:
            duration_sec = len(full_audio) / self.config.sample_rate

            if not final:
                if self._should_run_offline_fallback(full_audio, duration_sec):
                    try:
                        offline = self._asr.recognize_audio(
                            full_audio, self.config.sample_rate,
                        )
                        if offline and len(offline) >= len(final):
                            final = offline.strip()
                    except Exception as e:
                        log.warn(f"离线识别失败: {e}")
                else:
                    log.debug("[ASR] 跳过离线兜底（音频过短或能量过低）")

            # SV：说话人门控
            if not self._sv_accept(full_audio, duration_sec):
                log.info("[ASR] SV 拒绝本轮语音，已丢弃")
                return None

            # 多说话人识别
            if (
                self.config.enable_diarization
                and duration_sec >= self.config.diarization_min_audio_sec
            ):
                try:
                    self._init_diarization()
                    if self._diarization is not None:
                        user_id = self._identify_speaker(full_audio)
                        self._current_user_id = user_id
                        if self._agent and hasattr(self._agent, 'user_id'):
                            self._agent.user_id = user_id
                except Exception as e:
                    log.warn(f"说话人识别失败: {e}")

            # SER：情绪识别
            if (
                self.config.enable_ser
                and duration_sec >= (self.config.ser_min_audio_sec or 0.8)
            ):
                try:
                    self._init_ser()
                    if self._ser is not None:
                        t0_ser = time.perf_counter()
                        r: SERResult = self._ser.predict(
                            full_audio, sample_rate=self.config.sample_rate,
                        )
                        self._current_user_emotion = r.emotion9
                        log.debug(
                            f"[耗时] SER: {time.perf_counter() - t0_ser:.2f}s, "
                            f"emo={r.emotion9}, score={r.score:.2f}"
                        )
                except Exception as e:
                    log.debug(f"SER 推断失败（忽略）: {e}")

        final = self._collapse_repeated_asr_text(final)
        final = self._apply_punc(final)

        if final:
            log.debug(f"[ASR] 最终: '{final}'")
        return final or None

    def _listen_with_text(self) -> Optional[str]:
        """使用文本输入（调试模式）"""
        try:
            text = input("\n请输入 (或说 'quit' 退出): ").strip()
            return text if text else None
        except EOFError:
            return None

    # ------------------------------------------------------------------
    # 情绪解析
    # ------------------------------------------------------------------

    def _parse_emotion(self, text: str) -> tuple:
        """从 AI 回复中提取情绪标签，返回 (clean_text, emotion)。"""
        emotions_found = self._EMOTION_PATTERN.findall(text)
        emotion = "neutral"
        for e in emotions_found:
            if e.lower() in self._VALID_EMOTIONS:
                emotion = e.lower()
                break
        clean_text = self._EMOTION_PATTERN.sub("", text).strip()
        clean_text = re.sub(r'  +', ' ', clean_text)

        # 无显式标签时进行轻量规则推断
        if emotion == "neutral" and clean_text:
            inferred = self._emotion_classifier.classify(clean_text)
            if inferred.emotion in self._VALID_EMOTIONS:
                emotion = inferred.emotion

        return (clean_text or text.strip(), emotion)
