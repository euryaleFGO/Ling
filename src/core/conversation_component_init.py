# -*- coding: utf-8 -*-
"""
Component initialisation for AsyncConversationManager.

Encapsulates the lazy init logic for ASR, TTS, LLM Agent, and audio devices.
Designed to be mixed into ``AsyncConversationManager`` via multiple inheritance.
"""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

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
        """Initialise ASR (FunASR local or Whisper remote)."""
        if self._asr is not None:
            return

        if self.config.general.use_text_input:
            log.debug("[conversation] Text-input mode, skipping ASR init")
            self._asr = None
            return

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

        # FunASR local
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
                    logger.debug("Failed to load ASR model dir from AppSettings")
                for p in [
                    _PROJECT_ROOT / "models" / "ASR" / "paraformer-zh-streaming",
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
                    logger.debug("Failed to load VAD model dir from AppSettings")
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
                log.debug(
                    f"[conversation] ASR: FunASR local (device={asr_device}, "
                    f"chunk={stream_cfg.get('chunk_size')})"
                )
            else:
                log.warn(f"ASR model directory does not exist: {model_dir}")
                self._asr = None
        except Exception as e:
            log.warn(f"ASR init failed: {e}")
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
                default_paths = [
                    _PROJECT_ROOT / "models" / "TTS" / "CosyVoice2-0.5B",
                ]
                try:
                    from core.settings import AppSettings
                    s = AppSettings.load()
                    if s.tts_model_dir.exists():
                        default_paths.insert(0, s.tts_model_dir)
                except Exception:
                    logger.debug("Failed to load TTS model dir from AppSettings")
                for p in default_paths:
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
        log.debug("[conversation] Audio devices ready")

    # -- Aggregate init -----------------------------------------------------

    def initialize(self: "AsyncConversationManager"):
        """Initialize all sub-components."""
        log.debug("[conversation] Initialising async conversation system ...")
        self._init_audio()
        self._init_tts()
        self._init_agent()
        log.info("Async conversation system initialised")
