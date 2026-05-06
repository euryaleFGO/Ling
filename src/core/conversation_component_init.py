# -*- coding: utf-8 -*-
"""
Component initialisation for AsyncConversationManager.

Encapsulates the lazy init logic for ASR, TTS, LLM Agent, and audio devices.
Designed to be mixed into ``AsyncConversationManager`` via multiple inheritance.
"""

import logging
import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np

from core.log import log
from core.audio_io import AudioInput, AudioOutput, AudioConfig
from core.vad import VADConfig
from core.tts_cache import TTSCache

if TYPE_CHECKING:
    from core.conversation_manager_async import AsyncConversationManager

logger = logging.getLogger(__name__)

# Project root (used to locate default model directories)
_PROJECT_ROOT = Path(__file__).parent.parent.parent


# ============================================================
#  Mixin
# ============================================================

class ComponentInitMixin:
    """ASR / TTS / Agent / Audio device initialisation.

    All methods reference ``self.config`` and component slots
    (``_asr``, ``_tts``, ``_agent``, ``_audio_input``, ``_audio_output``, etc.)
    that live on the final ``AsyncConversationManager``.
    """

    # -- ASR helpers --------------------------------------------------------

    def _get_asr_stream_profile(self: "AsyncConversationManager") -> dict:
        """Return ASR streaming parameters for the configured profile."""
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

    def _resolve_asr_device(self: "AsyncConversationManager", requested: str) -> str:
        """Resolve the ASR device string; ``auto`` picks CUDA/CPU."""
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
                log.warn(f"ASR device '{requested}' unavailable, falling back to cpu")
                return "cpu"
            m = re.fullmatch(r"cuda:(\d+)", req)
            if m:
                idx = int(m.group(1))
                count = _cuda_count()
                if 0 <= idx < max(1, count):
                    return req
                fallback = "cuda:0" if count > 0 else "cpu"
                log.warn(
                    f"ASR device '{requested}' out of range (GPU count={count}), "
                    f"falling back to {fallback}"
                )
                return fallback
            if req == "cuda":
                return "cuda:0"
            log.warn(f"ASR device '{requested}' unavailable, falling back to cpu")
            return "cpu"

        return "cpu"

    # -- Init: ASR ----------------------------------------------------------

    def _init_asr(self: "AsyncConversationManager"):
        """Initialise ASR: remote first (if configured), then local fallback."""
        if self._asr is not None:
            return

        if self.config.general.use_text_input:
            log.debug("[conversation] Text-input mode, skipping ASR init")
            self._asr = None
            return

        # 1. Whisper 远程
        provider = (self.config.asr.provider or "funasr").lower()
        if provider == "whisper":
            try:
                from backend.asr.providers import WhisperRemoteProvider
                base = self.config.asr.whisper_api_base or "https://api.openai.com/v1"
                key = self.config.asr.whisper_api_key or ""
                self._asr = WhisperRemoteProvider(api_base=base, api_key=key)
                log.debug("[conversation] ASR: Whisper remote mode")
            except Exception as e:
                log.warn(f"Whisper ASR init failed: {e}")
                self._asr = None
            return

        # 2. 远程 FunASR（优先）
        remote_url = getattr(self.config.asr, "remote_url", None)
        if remote_url:
            try:
                from backend.asr.providers import FunASRRemoteProvider
                remote = FunASRRemoteProvider(base_url=remote_url)
                if remote._client.health_check():
                    self._asr = remote
                    log.info(f"[conversation] ASR: remote ({remote_url})")
                    return
                else:
                    log.warn(f"[conversation] ASR remote unavailable: {remote_url}, falling back to local")
            except Exception as e:
                log.warn(f"[conversation] ASR remote init failed: {e}, falling back to local")

        # 3. 本地 FunASR（回退）
        self._init_asr_local()

    def _init_asr_local(self: "AsyncConversationManager"):
        """Initialise local FunASR ASR."""
        try:
            from backend.asr.providers import FunASRProvider

            model_dir = self.config.asr.model_dir
            if not model_dir:
                for p in [
                    _PROJECT_ROOT / "models" / "ASR" / "paraformer-zh-streaming",
                ]:
                    if p.exists():
                        model_dir = str(p)
                        break

            vad_model = None
            if self.config.audio.use_vad:
                vad_model = self.config.asr.vad_model_dir
                if not vad_model:
                    for p in [
                        _PROJECT_ROOT / "models" / "ASR" / "fsmn-vad",
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
                log.info(
                    f"[conversation] ASR: local FunASR (device={asr_device}, "
                    f"chunk={stream_cfg.get('chunk_size')})"
                )
            else:
                log.warn(f"ASR model directory does not exist: {model_dir}")
                self._asr = None
        except Exception as e:
            log.warn(f"ASR local init failed: {e}")
            self._asr = None

    # -- Init: TTS ----------------------------------------------------------

    def _init_tts(self: "AsyncConversationManager"):
        """Initialise TTS (local or remote)."""
        if self._tts is not None:
            return

        # Prefer remote TTS
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
                    log.debug(f"[conversation] TTS remote ready: {self.config.tts.remote_url}")
                    return
                else:
                    log.warn(f"TTS remote unavailable: {self.config.tts.remote_url}")
            except Exception as e:
                log.warn(f"TTS remote init failed: {e}")

        # Local TTS
        try:
            from backend.tts.engine import CosyvoiceRealTimeTTS

            model_dir = self.config.tts.model_dir
            if not model_dir:
                for p in [
                    _PROJECT_ROOT / "models" / "TTS" / "CosyVoice2-0.5B",
                ]:
                    if p.exists():
                        model_dir = str(p)
                        break

            if model_dir and Path(model_dir).exists():
                self._tts = CosyvoiceRealTimeTTS(model_path=model_dir)
                self._tts_mode = "local"
                log.debug("[conversation] TTS local engine ready")
            else:
                log.warn(f"TTS model directory does not exist: {model_dir}")
                self._tts = None
                self._tts_mode = None
        except Exception as e:
            log.warn(f"TTS init failed: {e}")
            self._tts = None
            self._tts_mode = None

        # TTS cache
        if self._tts and self.config.tts.enable_cache:
            try:
                cache_dir = (
                    _PROJECT_ROOT / "cache" / "tts"
                    if self.config.tts.enable_cache
                    else None
                )
                self._tts_cache = TTSCache(
                    max_size=self.config.tts.cache_size,
                    cache_dir=cache_dir,
                    enable_disk_cache=False,
                )
                log.debug(
                    f"[conversation] TTS cache ready (size: {self.config.tts.cache_size})"
                )
                if self.config.tts.cache_common_phrases:
                    log.info(
                        f"[conversation] Pre-loading {len(self.config.tts.cache_common_phrases)} "
                        "common phrases ..."
                    )
            except Exception as e:
                log.warn(f"TTS cache init failed: {e}")
                self._tts_cache = None

    # -- Init: Agent --------------------------------------------------------

    def _init_agent(self: "AsyncConversationManager"):
        """Initialise the LLM agent."""
        if self._agent is not None:
            return

        try:
            from backend.llm.agent import Agent

            self._agent = Agent(user_id=self.config.general.user_id)
            self._agent.start_chat()
            log.debug("[conversation] Agent init complete")
        except Exception as e:
            log.error(f"Agent init failed: {e}")
            raise

    # -- Init: Diarization -------------------------------------------------

    def _init_diarization(self: "AsyncConversationManager"):
        """Initialise voiceprint diarization (speaker identification)."""
        if not self.config.diarization.enable:
            log.debug("[conversation] Diarization disabled in config")
            return

        if self._diarization is not None:
            return

        try:
            from core.sv_engine import SVEngine
            from core.voiceprint_database import VoiceprintDatabase
            from core.diarization_engine import DiarizationEngine
            from core.speaker_manager import SpeakerManager

            # 1. 初始化声纹引擎
            sv_device = self.config.diarization.device
            if sv_device == "auto":
                try:
                    import torch
                    sv_device = "cuda:0" if torch.cuda.is_available() else "cpu"
                except Exception:
                    sv_device = "cpu"

            sv_model = self.config.diarization.model_id or "campplus"
            self._sv = SVEngine(model_id=sv_model, device=sv_device)
            log.info(f"[conversation] SVEngine ready (model={sv_model}, device={sv_device})")

            # 2. 初始化声纹数据库
            storage_path = self.config.diarization.storage_path
            if not storage_path:
                storage_path = str(_PROJECT_ROOT / "data" / "voiceprints")
            self._voiceprint_db = VoiceprintDatabase(storage_path=Path(storage_path))
            log.info(f"[conversation] VoiceprintDatabase ready ({storage_path})")

            # 3. 初始化 SpeakerManager（用于 unknown 注册和改名）
            self._speaker_manager = SpeakerManager(
                sv_engine=self._sv,
                voiceprint_db=self._voiceprint_db,
            )

            # 4. 初始化 DiarizationEngine
            self._diarization = DiarizationEngine(
                sv_engine=self._sv,
                voiceprint_db=self._voiceprint_db,
                threshold=self.config.diarization.threshold,
                min_audio_sec=self.config.diarization.min_audio_sec,
                device=sv_device,
                timeout_ms=self.config.diarization.timeout_ms,
                speaker_manager=self._speaker_manager,
            )

            # 注入 speaker_manager 到 Agent（如果已初始化）
            if self._agent and hasattr(self._agent, 'set_speaker_manager'):
                self._agent.set_speaker_manager(self._speaker_manager)

            log.info(
                f"[conversation] Diarization ready "
                f"(threshold={self.config.diarization.threshold}, "
                f"auto_register={getattr(self.config.diarization, 'auto_register_unknown', True)})"
            )

        except Exception as e:
            log.warn(f"Diarization init failed: {e}")
            self._diarization = None
            self._sv = None
            self._voiceprint_db = None
            self._speaker_manager = None

    def _identify_speaker(self: "AsyncConversationManager", audio: np.ndarray) -> Optional[str]:
        """
        识别音频中的说话人

        Args:
            audio: 音频数据

        Returns:
            speaker_id 或 None
        """
        if self._diarization is None:
            return None

        try:
            result = self._diarization.identify(
                audio,
                sample_rate=self.config.audio.sample_rate,
            )

            if result.speaker_id and result.speaker_id != "unknown":
                old_user_id = self._current_user_id
                self._current_user_id = result.speaker_id

                # 更新 Agent 的 user_id
                if self._agent:
                    self._agent.user_id = result.speaker_id

                if old_user_id != result.speaker_id:
                    log.info(f"[conversation] Speaker changed: {old_user_id} -> {result.speaker_id} (score={result.score:.3f})")
                    if self._on_speaker_change_callback:
                        try:
                            self._on_speaker_change_callback(result.speaker_id, result.score)
                        except Exception as e:
                            log.debug(f"Speaker change callback failed: {e}")

                return result.speaker_id

            return result.speaker_id

        except Exception as e:
            log.warning(f"[conversation] Speaker identification failed: {e}")
            return None

    # -- Init: Audio devices ------------------------------------------------

    def _init_audio(self: "AsyncConversationManager"):
        """Initialise audio input/output devices."""
        self._init_asr()

        chunk_size = 5760  # default 360 ms
        if self._asr and hasattr(self._asr, "get_chunk_stride"):
            chunk_size = self._asr.get_chunk_stride()

        vad_config = VADConfig.preset(self.config.audio.vad_preset)
        vad_config.backend = self.config.audio.vad_backend
        vad_config.silence_duration = self.config.audio.silence_duration
        # 不再强制覆盖 min_speech_chunks，使用 preset 默认值（balanced=1）
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
        log.debug("[conversation] Audio devices ready")

    # -- Aggregate init -----------------------------------------------------

    def initialize(self: "AsyncConversationManager"):
        """Initialize all sub-components."""
        log.debug("[conversation] Initialising async conversation system ...")
        self._init_audio()
        self._init_tts()
        self._init_agent()
        self._init_diarization()
        log.info("Async conversation system initialised")
