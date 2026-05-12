#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SER 服务器 - 语音情绪识别远程服务

独立部署，不需要完整项目目录。
仅依赖: transformers, torch, flask, numpy

端点:
  /health          健康检查
  /ser/predict     情绪识别（接收 base64 音频，返回情绪标签）
"""

import os
import logging
import base64
from pathlib import Path

import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ser_server")

app = Flask(__name__)
CORS(app)

# ---- 设备检测 ----

def _detect_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            logger.info(f"[Device] GPU: {name}")
            return "cuda:0"
    except Exception:
        pass
    logger.info("[Device] CPU")
    return "cpu"


# ============================================================
#  SER 引擎（单例，懒加载）
# ============================================================

class SEREngine:
    DEFAULT_MODEL_ID = "superb/wav2vec2-large-superb-er"
    DEFAULT_LABEL_MAP = {
        "angry": "anger",
        "happy": "joy",
        "sad": "sadness",
        "neutral": "neutral",
    }

    def __init__(self, model_id: str = None, device: str = "auto"):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.device = device
        self._pipe = None
        self._label_map = {k.lower(): v for k, v in self.DEFAULT_LABEL_MAP.items()}

    def _resolve_device(self) -> int:
        req = (self.device or "auto").strip().lower()
        if req == "cpu":
            return -1
        if req.startswith("cuda"):
            try:
                import torch
                if torch.cuda.is_available():
                    return int(req.split(":", 1)[1]) if ":" in req else 0
            except Exception:
                pass
            return -1
        try:
            import torch
            return 0 if torch.cuda.is_available() else -1
        except Exception:
            return -1

    def _ensure_pipe(self):
        if self._pipe is not None:
            return
        from transformers import pipeline
        # 优先加载本地模型（打包部署时使用）
        local_model = Path(__file__).parent / "model"
        if local_model.exists() and any(local_model.iterdir()):
            model_path = str(local_model)
            logger.info(f"[SER] Loading local model: {model_path}")
        else:
            model_path = self.model_id
            logger.info(f"[SER] Loading model: {model_path}")
        self._pipe = pipeline(
            task="audio-classification",
            model=model_path,
            device=self._resolve_device(),
        )
        logger.info("[SER] Model loaded")

    def predict(self, audio: np.ndarray, sample_rate: int = 16000) -> dict:
        self._ensure_pipe()
        if audio.dtype == np.int16:
            audio = (audio.astype(np.float32) / 32768.0).reshape(-1)
        else:
            audio = audio.astype(np.float32).reshape(-1)
            m = float(np.max(np.abs(audio))) if audio.size else 0.0
            if m > 2.0:
                audio = audio / 32768.0

        if audio.size == 0:
            return {"label": "neutral", "score": 0.0, "emotion9": "neutral"}

        out = self._pipe({"array": audio, "sampling_rate": int(sample_rate)})
        if not out:
            return {"label": "neutral", "score": 0.0, "emotion9": "neutral"}

        top = out[0]
        raw_label = str(top.get("label", "")).strip()
        score = float(top.get("score", 0.0) or 0.0)
        mapped = self._label_map.get(raw_label.lower(), "neutral")
        return {"label": raw_label, "score": score, "emotion9": mapped}


# 全局单例
_engine: SEREngine | None = None


def _get_engine() -> SEREngine:
    global _engine
    if _engine is None:
        model_id = os.environ.get("SER_MODEL_ID", "")
        device = os.environ.get("SER_DEVICE", "auto")
        _engine = SEREngine(model_id=model_id or None, device=device)
    return _engine


# ============================================================
#  HTTP 端点
# ============================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "ser"})


@app.route("/ser/predict", methods=["POST"])
def ser_predict():
    """
    请求 JSON:
    {
        "audio": "<base64 编码的 PCM float32 或 WAV>",
        "sample_rate": 16000
    }

    响应 JSON:
    {
        "label": "happy",
        "score": 0.95,
        "emotion9": "joy"
    }
    """
    data = request.get_json(force=True, silent=True)
    if not data or "audio" not in data:
        return jsonify({"error": "missing 'audio' field"}), 400

    try:
        raw = base64.b64decode(data["audio"])
        audio = np.frombuffer(raw, dtype=np.float32)
    except Exception as e:
        return jsonify({"error": f"decode failed: {e}"}), 400

    sample_rate = int(data.get("sample_rate", 16000))

    try:
        engine = _get_engine()
        result = engine.predict(audio, sample_rate=sample_rate)
        return jsonify(result)
    except Exception as e:
        logger.error(f"[SER] predict error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================
#  启动
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SER Server")
    parser.add_argument("--port", type=int, default=5003)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--model-id", type=str, default="")
    parser.add_argument("--device", type=str, default="auto")
    args = parser.parse_args()

    if args.model_id:
        os.environ["SER_MODEL_ID"] = args.model_id
    if args.device:
        os.environ["SER_DEVICE"] = args.device

    # 预加载模型
    _get_engine()

    logger.info(f"[SER Server] Starting on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
