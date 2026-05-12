# -*- coding: utf-8 -*-
"""
Speaker verification engine for ASR gating.

Design goals:
- Optional and fail-safe: do not block ASR when model is unavailable unless caller enforces.
- Lazy-load model and parse multiple possible FunASR output shapes.
- Enrollment by reference audio once, then cosine-similarity verification.
"""

from __future__ import annotations

import logging
import os
import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

import numpy as np


@dataclass
class SVResult:
    accepted: bool
    score: float
    threshold: float
    reason: str = ""


def _ensure_project_modelscope_cache() -> None:
    """
    未设置 MODELSCOPE_CACHE 时，将缓存目录设为项目根下的 .modelscope_cache。
    若用户已手动设置环境变量，则完全尊重用户配置。
    """
    if (os.environ.get("MODELSCOPE_CACHE") or "").strip():
        return
    root = Path(__file__).resolve().parents[2]
    cache_dir = root / ".modelscope_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MODELSCOPE_CACHE"] = str(cache_dir)
    os.environ.setdefault("MODELSCOPE_HOME", str(cache_dir))


class SVEngine:
    DEFAULT_MODEL_ID = "iic/speech_campplus_sv_zh-cn_16k-common"

    def __init__(self, model_id: str | None = None, device: str = "auto", threshold: float = 0.38):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.device = device
        self.threshold = float(threshold)
        self._model = None
        self._model_ready = False
        self._model_error: str = ""
        self._enroll_emb: Optional[np.ndarray] = None

    def _resolve_device(self) -> str:
        req = (self.device or "auto").strip().lower()
        if req == "cpu":
            return "cpu"
        if req in ("cuda", "cuda:0"):
            req = "cuda:0"
        if req.startswith("cuda"):
            try:
                import torch
                if torch.cuda.is_available():
                    return req
            except Exception as e:
                logger.debug(f"Failed to check CUDA availability for explicit device request, falling back to cpu: {e}")
                return "cpu"
            return "cpu"
        try:
            import torch
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        except Exception as e:
            logger.debug(f"Failed to import torch or check CUDA availability, falling back to cpu: {e}")
            return "cpu"

    def _ensure_model(self):
        if self._model_ready:
            return
        if self._model_error:
            raise RuntimeError(self._model_error)
        try:
            _ensure_project_modelscope_cache()

            # Set deterministic CUDA operations BEFORE loading model
            try:
                import torch
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False
            except Exception:
                pass

            from funasr import AutoModel
            self._model = AutoModel(model=self.model_id, device=self._resolve_device(), disable_update=True)

            # Explicitly set eval mode — Dropout / BatchNorm must not
            # use training-time stochastic behaviour during inference.
            self._set_eval_mode()

            self._model_ready = True
        except Exception as e:
            self._model_error = f"load_failed:{type(e).__name__}:{e}"
            raise

    def _set_eval_mode(self) -> None:
        """Recursively set all torch.nn.Module sub-components to eval mode.

        FunASR ``AutoModel`` is a wrapper, not an ``nn.Module`` itself.
        The actual model lives at various depths depending on the pipeline.
        We walk the common attribute paths *and* call ``named_children()``
        on anything that looks like a module.
        """
        try:
            import torch
            visited: set[int] = set()
            queue = [self._model]
            while queue:
                obj = queue.pop(0)
                oid = id(obj)
                if oid in visited:
                    continue
                visited.add(oid)

                if isinstance(obj, torch.nn.Module):
                    obj.eval()

                # Walk PyTorch children (the standard way)
                if hasattr(obj, "named_children"):
                    try:
                        for _, child in obj.named_children():
                            if id(child) not in visited:
                                queue.append(child)
                    except Exception:
                        pass

                # Also probe common FunASR wrapper attributes
                for attr in ("model", "_model", "encoder", "backbone",
                             "frontend", "sv_model", "asr_model"):
                    try:
                        child = getattr(obj, attr, None)
                        if child is not None and id(child) not in visited:
                            queue.append(child)
                    except Exception:
                        pass

            logger.debug("SVEngine: eval mode set on all sub-modules")
        except Exception as exc:
            logger.debug(f"SVEngine: could not set eval mode: {exc}")

    @staticmethod
    def _to_float32(audio: np.ndarray) -> np.ndarray:
        if audio is None:
            return np.zeros(0, dtype=np.float32)
        if not isinstance(audio, np.ndarray):
            audio = np.asarray(audio)
        if audio.size == 0:
            return np.zeros(0, dtype=np.float32)
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.reshape(-1)
        return audio

    @staticmethod
    def _l2norm(v: np.ndarray) -> np.ndarray:
        n = float(np.linalg.norm(v))
        if n <= 1e-8:
            return v
        return v / n

    @staticmethod
    def _extract_embedding(res) -> Optional[np.ndarray]:
        _PREFERRED_KEYS = ("spk_embedding", "speaker_embedding",
                           "embedding", "embs", "spk_emb")

        def _from_any(x):
            if x is None:
                return None
            if isinstance(x, np.ndarray):
                return x.astype(np.float32).reshape(-1)
            if isinstance(x, (list, tuple)):
                if len(x) == 0:
                    return None
                # list of floats or nested list
                if isinstance(x[0], (int, float, np.floating)):
                    return np.asarray(x, dtype=np.float32).reshape(-1)
                return _from_any(x[0])
            if hasattr(x, "detach") and hasattr(x, "cpu"):
                try:
                    return np.asarray(x.detach().cpu().numpy(), dtype=np.float32).reshape(-1)
                except Exception as e:
                    logger.debug(f"Failed to convert tensor to numpy embedding: {e}")
                    return None
            return None

        def _extract_from_dict(d):
            for k in _PREFERRED_KEYS:
                if k in d:
                    emb = _from_any(d.get(k))
                    if emb is not None and emb.size > 0:
                        logger.debug(f"_extract_embedding: found key='{k}', "
                                     f"shape={emb.shape}")
                        return emb
            return None

        if isinstance(res, list) and len(res) > 0:
            item = res[0]
            if isinstance(item, dict):
                emb = _extract_from_dict(item)
                if emb is not None:
                    return emb
            else:
                # Maybe list of embeddings directly
                emb = _from_any(item)
                if emb is not None and emb.size > 0:
                    logger.debug(f"_extract_embedding: extracted from "
                                 f"list[0], shape={emb.shape}")
                    return emb
        if isinstance(res, dict):
            emb = _extract_from_dict(res)
            if emb is not None:
                return emb
        # Last fallback: maybe raw embedding array directly
        emb = _from_any(res)
        if emb is not None and emb.size > 0:
            logger.debug(f"_extract_embedding: fallback raw, shape={emb.shape}")
            return emb
        return None

    def embed(self, audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        self._ensure_model()
        a = self._to_float32(audio)
        if a.size == 0:
            raise ValueError("empty_audio")

        # Resample to 16kHz if needed (model expects 16kHz)
        if sample_rate != 16000:
            try:
                import librosa
                a = librosa.resample(a, orig_sr=sample_rate, target_sr=16000)
            except ImportError:
                logger.warning("librosa not available, cannot resample from %d to 16000", sample_rate)

        import torch
        with torch.no_grad():
            out = self._model.generate(input=a)

        emb = self._extract_embedding(out)
        if emb is None:
            # Log the raw output for debugging
            logger.error(f"SVEngine: _extract_embedding returned None. "
                         f"raw type={type(out)}, "
                         f"raw={repr(out)[:500]}")
            raise RuntimeError("sv_embedding_not_found")

        logger.debug(f"SVEngine: extracted embedding dim={emb.shape}, "
                     f"first5={emb[:5]}")
        return self._l2norm(emb)

    def enroll_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        emb = self.embed(audio, sample_rate=sample_rate)
        self._enroll_emb = emb
        return emb

    def enroll_file(self, path: str | Path) -> np.ndarray:
        import soundfile as sf
        audio, sr = sf.read(str(path))
        if isinstance(audio, np.ndarray) and audio.ndim > 1:
            audio = audio.mean(axis=1)
        return self.enroll_audio(audio, sample_rate=int(sr))

    def is_enrolled(self) -> bool:
        return self._enroll_emb is not None and self._enroll_emb.size > 0

    def verify(self, audio: np.ndarray, sample_rate: int = 16000, threshold: float | None = None) -> SVResult:
        th = float(self.threshold if threshold is None else threshold)
        if not self.is_enrolled():
            return SVResult(accepted=True, score=1.0, threshold=th, reason="not_enrolled")

        try:
            q = self.embed(audio, sample_rate=sample_rate)
            score = float(np.dot(self._enroll_emb, q))
            return SVResult(accepted=score >= th, score=score, threshold=th, reason="cosine")
        except Exception as e:
            return SVResult(accepted=True, score=0.0, threshold=th, reason=f"fail_open:{type(e).__name__}")


class RemoteSVEngine:
    """远程声纹嵌入提取客户端（HTTP）。

    接口与 SVEngine.embed() 兼容，可直接替换。
    """

    def __init__(self, base_url: str = "http://localhost:5003", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = None

    def _ensure_session(self):
        if self._session is not None: return
        import requests
        self._session = requests.Session()

    def embed(self, audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        self._ensure_session()
        # 归一化为 float32
        if isinstance(audio, np.ndarray):
            if audio.dtype == np.int16:
                audio_f32 = (audio.astype(np.float32) / 32768.0).reshape(-1)
            else:
                audio_f32 = audio.astype(np.float32).reshape(-1)
                if float(np.max(np.abs(audio_f32))) > 2.0:
                    audio_f32 = audio_f32 / 32768.0
        else:
            audio_f32 = np.asarray(audio, dtype=np.float32).reshape(-1)

        audio_b64 = base64.b64encode(audio_f32.tobytes()).decode("ascii")

        last_err = None
        for attempt in range(3):
            try:
                resp = self._session.post(
                    f"{self.base_url}/sv/embed",
                    json={"audio": audio_b64, "sample_rate": sample_rate},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                emb_bytes = base64.b64decode(data["embedding"])
                return np.frombuffer(emb_bytes, dtype=np.float32).copy()
            except Exception as e:
                last_err = e
                if attempt < 2: time.sleep(0.5 * (attempt + 1))

        logger.warning(f"[SV-Remote] retries failed: {last_err}")
        raise RuntimeError(f"sv_remote_failed: {last_err}")

    def health_check(self) -> bool:
        self._ensure_session()
        try:
            resp = self._session.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def close(self):
        if self._session:
            self._session.close()
            self._session = None
