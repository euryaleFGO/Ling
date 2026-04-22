# -*- coding: utf-8 -*-
"""
Punctuation restoration engine for ASR text.

Design goals:
- Optional and fail-safe: if model loading/inference fails, return heuristic result.
- Lazy-load model to avoid startup latency.
- Work with FunASR AutoModel when available.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re


@dataclass
class PUNCResult:
    text: str
    used_model: bool
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


class PUNCEngine:
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
    def _heuristic_restore(text: str) -> str:
        s = (text or "").strip()
        if not s:
            return ""
        s = re.sub(r"\s+", " ", s)
        # Basic punctuation normalization
        s = s.replace(" ,", ",").replace(" .", ".")
        # Add a terminal punctuation mark for long Chinese text if missing.
        if re.search(r"[\u4e00-\u9fff]", s) and not re.search(r"[。！？!?]$", s) and len(s) >= 8:
            s += "。"
        return s

    @staticmethod
    def _extract_text_from_result(res) -> str:
        if not res:
            return ""
        # Typical FunASR return shape: list[dict]
        if isinstance(res, list) and len(res) > 0:
            item = res[0]
            if isinstance(item, dict):
                t = item.get("text") or item.get("preds")
                if isinstance(t, list):
                    return "".join(str(x) for x in t)
                return str(t or "")
        if isinstance(res, dict):
            t = res.get("text") or res.get("preds")
            if isinstance(t, list):
                return "".join(str(x) for x in t)
            return str(t or "")
        return ""

    def restore(self, text: str) -> PUNCResult:
        src = (text or "").strip()
        if not src:
            return PUNCResult(text="", used_model=False, reason="empty_input")

        try:
            self._ensure_model()
            out = self._model.generate(input=src)
            fixed = self._extract_text_from_result(out).strip()
            if fixed:
                return PUNCResult(text=fixed, used_model=True, reason="funasr_model")
            return PUNCResult(text=self._heuristic_restore(src), used_model=False, reason="empty_model_output")
        except Exception as e:
            return PUNCResult(text=self._heuristic_restore(src), used_model=False, reason=f"fallback:{type(e).__name__}")
