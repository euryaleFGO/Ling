# -*- coding: utf-8 -*-
"""
SER (Speech Emotion Recognition) - 语音情绪识别

目标：
- 输入：16kHz 单声道音频（numpy float32 [-1,1] 或 int16）
- 输出：离散情绪标签（默认 4 类：angry/happy/sad/neutral），并映射到项目的 Live2D 9 类情绪集合

实现策略：
- 使用 HuggingFace Transformers 的 audio-classification pipeline（预训练模型）
- 懒加载 + 可选 GPU
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np


def _ensure_project_hf_home() -> None:
    """
    未设置 HF_HOME 时，将 Hugging Face 缓存目录设为「项目根/.hf_cache」，
    避免默认落在用户目录（如 C 盘）且与仓库同盘便于迁移。
    若已设置环境变量 HF_HOME，则完全尊重用户配置。
    """
    if (os.environ.get("HF_HOME") or "").strip():
        return
    root = Path(__file__).resolve().parents[2]
    hf = root / ".hf_cache"
    hf.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(hf)


@dataclass
class SERResult:
    label: str              # 原始模型标签（如 angry/happy/sad/neutral）
    score: float            # 置信度
    emotion9: str           # 映射到 9 类（neutral/joy/anger/sadness/surprise/shy/think/fear/cry）
    reason: str = ""        # 说明/来源


class SEREngine:
    """
    基于 transformers pipeline 的语音情绪识别引擎。
    """

    # 默认使用 SUPERB ER 预训练模型（16kHz）
    DEFAULT_MODEL_ID = "superb/wav2vec2-large-superb-er"

    # SUPERB ER 常见 4 类到项目 9 类的映射
    DEFAULT_LABEL_MAP: Dict[str, str] = {
        "angry": "anger",
        "happy": "joy",
        "sad": "sadness",
        "neutral": "neutral",
    }

    def __init__(
        self,
        model_id: str = None,
        device: str = "auto",
        label_map: Optional[Dict[str, str]] = None,
    ):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.device = device
        self.label_map = {k.lower(): v for k, v in (label_map or self.DEFAULT_LABEL_MAP).items()}
        self._pipe = None

    def _resolve_device(self) -> int:
        """
        transformers pipeline 的 device:
        -1 表示 CPU
         0/1/... 表示 CUDA device index
        """
        req = (self.device or "auto").strip().lower()
        if req == "cpu":
            return -1
        if req.startswith("cuda"):
            # cuda 或 cuda:0
            try:
                import torch
                if torch.cuda.is_available():
                    if ":" in req:
                        return int(req.split(":", 1)[1])
                    return 0
            except Exception:
                return -1
            return -1
        # auto
        try:
            import torch
            return 0 if torch.cuda.is_available() else -1
        except Exception:
            return -1

    def _ensure_pipe(self):
        if self._pipe is not None:
            return
        _ensure_project_hf_home()
        from transformers import pipeline
        self._pipe = pipeline(
            task="audio-classification",
            model=self.model_id,
            device=self._resolve_device(),
        )

    @staticmethod
    def _to_float32(audio: np.ndarray) -> np.ndarray:
        if audio is None:
            return np.zeros(0, dtype=np.float32)
        if audio.dtype == np.int16:
            return (audio.astype(np.float32) / 32768.0).reshape(-1)
        a = audio.astype(np.float32).reshape(-1)
        # 容错：偶发未归一化 float32
        m = float(np.max(np.abs(a))) if a.size else 0.0
        if m > 2.0:
            a = a / 32768.0
        return a

    def predict(self, audio: np.ndarray, sample_rate: int = 16000) -> SERResult:
        self._ensure_pipe()
        a = self._to_float32(audio)
        if a.size == 0:
            return SERResult(label="neutral", score=0.0, emotion9="neutral", reason="empty_audio")

        # pipeline 返回按 score 排序的 list[dict]
        out = self._pipe({"array": a, "sampling_rate": int(sample_rate)})
        if not out:
            return SERResult(label="neutral", score=0.0, emotion9="neutral", reason="no_output")

        top = out[0]
        raw_label = str(top.get("label", "")).strip()
        score = float(top.get("score", 0.0) or 0.0)
        mapped = self.label_map.get(raw_label.lower(), "neutral")
        return SERResult(label=raw_label, score=score, emotion9=mapped, reason=f"hf:{self.model_id}")

