# -*- coding: utf-8 -*-
"""
Speaker verification engine for ASR gating.

Design goals:
- Optional and fail-safe: do not block ASR when model is unavailable unless caller enforces.
- Lazy-load model and parse multiple possible FunASR output shapes.
- Enrollment by reference audio once, then cosine-similarity verification.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
            except Exception:
                return "cpu"
            return "cpu"
        try:
            import torch
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def _ensure_model(self):
        if self._model_ready:
            return
        if self._model_error:
            raise RuntimeError(self._model_error)
        try:
            _ensure_project_modelscope_cache()
            from funasr import AutoModel
            self._model = AutoModel(model=self.model_id, device=self._resolve_device(), disable_update=True)
            self._model_ready = True
        except Exception as e:
            self._model_error = f"load_failed:{type(e).__name__}:{e}"
            raise

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
                except Exception:
                    return None
            return None

        if isinstance(res, list) and len(res) > 0:
            item = res[0]
            if isinstance(item, dict):
                for k in ("spk_embedding", "speaker_embedding", "embedding", "embs", "spk_emb"):
                    if k in item:
                        emb = _from_any(item.get(k))
                        if emb is not None and emb.size > 0:
                            return emb
        if isinstance(res, dict):
            for k in ("spk_embedding", "speaker_embedding", "embedding", "embs", "spk_emb"):
                if k in res:
                    emb = _from_any(res.get(k))
                    if emb is not None and emb.size > 0:
                        return emb
        # Last fallback: maybe raw embedding array directly
        emb = _from_any(res)
        if emb is not None and emb.size > 0:
            return emb
        return None

    def embed(self, audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        self._ensure_model()
        a = self._to_float32(audio)
        if a.size == 0:
            raise ValueError("empty_audio")
        out = self._model.generate(input=a)
        emb = self._extract_embedding(out)
        if emb is None:
            raise RuntimeError("sv_embedding_not_found")
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
