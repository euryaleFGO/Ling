# -*- coding: utf-8 -*-
"""
Punctuation restoration engine for ASR output.

Uses FunASR's CT-Transformer model to add punctuation to raw ASR text.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _ensure_project_modelscope_cache() -> None:
    if (os.environ.get("MODELSCOPE_CACHE") or "").strip():
        return
    root = Path(__file__).resolve().parents[2]
    cache_dir = root / ".modelscope_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MODELSCOPE_CACHE"] = str(cache_dir)


class PuncEngine:
    DEFAULT_MODEL_ID = "iic/punc_ct-transformer_cn-en-common-vocab471067-large"

    def __init__(self, model_id: str | None = None, device: str = "auto"):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.device = device
        self._model = None
        self._model_ready = False
        self._model_error: str = ""

    def _resolve_device(self) -> str:
        req = (self.device or "auto").strip().lower()
        if req == "cpu":
            return "cpu"
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
            self._model = AutoModel(
                model=self.model_id,
                device=self._resolve_device(),
                disable_update=True,
            )
            self._model_ready = True
        except Exception as e:
            self._model_error = f"load_failed:{type(e).__name__}:{e}"
            raise

    def add_punctuation(self, text: str) -> str:
        """Add punctuation to raw ASR text.

        Args:
            text: Raw ASR output without punctuation.

        Returns:
            Text with punctuation restored. Returns original on failure.
        """
        if not text or not text.strip():
            return text

        try:
            self._ensure_model()
            result = self._model.generate(input=text.strip())
            if result and isinstance(result, list) and len(result) > 0:
                item = result[0]
                if isinstance(item, dict):
                    return item.get("text", text)
                if isinstance(item, str):
                    return item
            return text
        except Exception as e:
            logger.debug(f"[PUNC] punctuation failed: {e}")
            return text
