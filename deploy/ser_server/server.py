#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一推理服务器 - SER + SV + PUNC

独立部署，不需要完整项目目录。
依赖: funasr, transformers, torch, flask, numpy

端点:
  /health           健康检查
  /ser/predict      情绪识别（音频 → 情绪标签）
  /sv/embed         声纹嵌入提取（音频 → embedding 向量）
  /punc/add         标点恢复（文本 → 带标点文本）
"""

import os
import logging
import base64
from pathlib import Path

# HuggingFace 镜像（国内服务器访问不了 huggingface.co 时使用）
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("inference_server")

app = Flask(__name__)
CORS(app)


# ============================================================
#  SER 引擎
# ============================================================

class SEREngine:
    DEFAULT_MODEL_ID = "superb/wav2vec2-large-superb-er"
    DEFAULT_LABEL_MAP = {
        "angry": "anger", "happy": "joy", "sad": "sadness", "neutral": "neutral",
    }

    def __init__(self, model_id=None, device="auto"):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.device = device
        self._pipe = None
        self._label_map = {k.lower(): v for k, v in self.DEFAULT_LABEL_MAP.items()}

    def _resolve_device(self) -> int:
        req = (self.device or "auto").strip().lower()
        if req == "cpu": return -1
        if req.startswith("cuda"):
            try:
                import torch
                if torch.cuda.is_available():
                    return int(req.split(":", 1)[1]) if ":" in req else 0
            except Exception: pass
            return -1
        try:
            import torch
            return 0 if torch.cuda.is_available() else -1
        except Exception: return -1

    def _ensure_pipe(self):
        if self._pipe is not None: return
        from transformers import pipeline
        logger.info(f"[SER] Loading model: {self.model_id}")
        self._pipe = pipeline(task="audio-classification", model=self.model_id, device=self._resolve_device())
        logger.info("[SER] Model loaded")

    def predict(self, audio, sample_rate=16000):
        self._ensure_pipe()
        audio = _to_float32(audio)
        if audio.size == 0:
            return {"label": "neutral", "score": 0.0, "emotion9": "neutral"}
        out = self._pipe({"array": audio, "sampling_rate": int(sample_rate)})
        if not out: return {"label": "neutral", "score": 0.0, "emotion9": "neutral"}
        top = out[0]
        raw_label = str(top.get("label", "")).strip()
        score = float(top.get("score", 0.0) or 0.0)
        return {"label": raw_label, "score": score, "emotion9": self._label_map.get(raw_label.lower(), "neutral")}


# ============================================================
#  SV 引擎（声纹嵌入提取）
# ============================================================

class SVEngine:
    DEFAULT_MODEL_ID = "iic/speech_campplus_sv_zh-cn_16k-common"

    def __init__(self, model_id=None, device="auto"):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.device = device
        self._model = None

    def _resolve_device(self) -> str:
        req = (self.device or "auto").strip().lower()
        if req == "cpu": return "cpu"
        if req.startswith("cuda"):
            try:
                import torch
                if torch.cuda.is_available(): return req
            except Exception: pass
            return "cpu"
        try:
            import torch
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        except Exception: return "cpu"

    def _ensure_model(self):
        if self._model is not None: return
        from funasr import AutoModel
        logger.info(f"[SV] Loading model: {self.model_id}")
        self._model = AutoModel(model=self.model_id, device=self._resolve_device(), disable_update=True)
        logger.info("[SV] Model loaded")

    def embed(self, audio, sample_rate=16000):
        self._ensure_model()
        audio = _to_float32(audio)
        if audio.size == 0: raise ValueError("empty_audio")
        if sample_rate != 16000:
            import librosa
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)
        import torch
        with torch.no_grad():
            out = self._model.generate(input=audio)
        emb = _extract_embedding(out)
        if emb is None: raise RuntimeError("sv_embedding_not_found")
        # L2 normalize
        n = float(np.linalg.norm(emb))
        if n > 1e-8: emb = emb / n
        return emb


# ============================================================
#  PUNC 引擎（标点恢复）
# ============================================================

class PuncEngine:
    DEFAULT_MODEL_ID = "iic/punc_ct-transformer_cn-en-common-vocab471067-large"

    def __init__(self, model_id=None, device="auto"):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.device = device
        self._model = None

    def _resolve_device(self) -> str:
        req = (self.device or "auto").strip().lower()
        if req == "cpu": return "cpu"
        if req.startswith("cuda"):
            try:
                import torch
                if torch.cuda.is_available(): return req
            except Exception: pass
            return "cpu"
        try:
            import torch
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        except Exception: return "cpu"

    def _ensure_model(self):
        if self._model is not None: return
        from funasr import AutoModel
        logger.info(f"[PUNC] Loading model: {self.model_id}")
        self._model = AutoModel(model=self.model_id, device=self._resolve_device(), disable_update=True)
        logger.info("[PUNC] Model loaded")

    def add_punctuation(self, text):
        if not text or not text.strip(): return text
        self._ensure_model()
        result = self._model.generate(input=text.strip())
        if result and isinstance(result, list) and len(result) > 0:
            item = result[0]
            if isinstance(item, dict): return item.get("text", text)
            if isinstance(item, str): return item
        return text


# ============================================================
#  工具函数
# ============================================================

def _to_float32(audio):
    if isinstance(audio, np.ndarray):
        if audio.dtype == np.int16:
            return (audio.astype(np.float32) / 32768.0).reshape(-1)
        a = audio.astype(np.float32).reshape(-1)
        if float(np.max(np.abs(a))) > 2.0: a = a / 32768.0
        return a
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def _extract_embedding(res):
    _KEYS = ("spk_embedding", "speaker_embedding", "embedding", "embs", "spk_emb")
    def _from_any(x):
        if x is None: return None
        if isinstance(x, np.ndarray): return x.astype(np.float32).reshape(-1)
        if isinstance(x, (list, tuple)):
            if not x: return None
            if isinstance(x[0], (int, float, np.floating)): return np.asarray(x, dtype=np.float32).reshape(-1)
            return _from_any(x[0])
        if hasattr(x, "detach") and hasattr(x, "cpu"):
            return np.asarray(x.detach().cpu().numpy(), dtype=np.float32).reshape(-1)
        return None
    def _from_dict(d):
        for k in _KEYS:
            if k in d:
                emb = _from_any(d[k])
                if emb is not None and emb.size > 0: return emb
        return None
    if isinstance(res, list) and res:
        item = res[0]
        if isinstance(item, dict):
            emb = _from_dict(item)
            if emb is not None: return emb
        else:
            emb = _from_any(item)
            if emb is not None and emb.size > 0: return emb
    if isinstance(res, dict):
        emb = _from_dict(res)
        if emb is not None: return emb
    return _from_any(res)


# ============================================================
#  全局单例
# ============================================================

_ser_engine = None
_sv_engine = None
_punc_engine = None

def _get_ser():
    global _ser_engine
    if _ser_engine is None:
        _ser_engine = SEREngine(model_id=os.environ.get("SER_MODEL_ID") or None, device=os.environ.get("SER_DEVICE", "auto"))
    return _ser_engine

def _get_sv():
    global _sv_engine
    if _sv_engine is None:
        _sv_engine = SVEngine(model_id=os.environ.get("SV_MODEL_ID") or None, device=os.environ.get("SV_DEVICE", "auto"))
    return _sv_engine

def _get_punc():
    global _punc_engine
    if _punc_engine is None:
        _punc_engine = PuncEngine(model_id=os.environ.get("PUNC_MODEL_ID") or None, device=os.environ.get("PUNC_DEVICE", "auto"))
    return _punc_engine


# ============================================================
#  HTTP 端点
# ============================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "inference", "engines": ["ser", "sv", "punc"]})


@app.route("/ser/predict", methods=["POST"])
def ser_predict():
    """情绪识别: {audio: base64_float32, sample_rate: 16000} → {label, score, emotion9}"""
    data = request.get_json(force=True, silent=True)
    if not data or "audio" not in data:
        return jsonify({"error": "missing 'audio' field"}), 400
    try:
        raw = base64.b64decode(data["audio"])
        audio = np.frombuffer(raw, dtype=np.float32)
    except Exception as e:
        return jsonify({"error": f"decode failed: {e}"}), 400
    try:
        result = _get_ser().predict(audio, int(data.get("sample_rate", 16000)))
        return jsonify(result)
    except Exception as e:
        logger.error(f"[SER] error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/sv/embed", methods=["POST"])
def sv_embed():
    """声纹嵌入: {audio: base64_float32, sample_rate: 16000} → {embedding: base64_float32, dim: int}"""
    data = request.get_json(force=True, silent=True)
    if not data or "audio" not in data:
        return jsonify({"error": "missing 'audio' field"}), 400
    try:
        raw = base64.b64decode(data["audio"])
        audio = np.frombuffer(raw, dtype=np.float32)
    except Exception as e:
        return jsonify({"error": f"decode failed: {e}"}), 400
    try:
        emb = _get_sv().embed(audio, int(data.get("sample_rate", 16000)))
        emb_b64 = base64.b64encode(emb.tobytes()).decode("ascii")
        return jsonify({"embedding": emb_b64, "dim": int(emb.shape[0])})
    except Exception as e:
        logger.error(f"[SV] error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/punc/add", methods=["POST"])
def punc_add():
    """标点恢复: {text: "你好"} → {text: "你好。"}"""
    data = request.get_json(force=True, silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "missing 'text' field"}), 400
    try:
        result = _get_punc().add_punctuation(data["text"])
        return jsonify({"text": result})
    except Exception as e:
        logger.error(f"[PUNC] error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================
#  启动
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Unified Inference Server (SER + SV + PUNC)")
    parser.add_argument("--port", type=int, default=5003)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--preload", nargs="*", default=["ser", "punc"],
                        help="Which engines to preload (default: ser punc). Use 'all' for all three.")
    args = parser.parse_args()

    if args.device:
        os.environ.setdefault("SER_DEVICE", args.device)
        os.environ.setdefault("SV_DEVICE", args.device)
        os.environ.setdefault("PUNC_DEVICE", args.device)

    preload = args.preload
    if "all" in preload: preload = ["ser", "sv", "punc"]

    logger.info(f"[Server] Preloading engines: {preload}")
    if "ser" in preload:
        logger.info("[Server] Loading SER...")
        _get_ser()._ensure_pipe()
    if "sv" in preload:
        logger.info("[Server] Loading SV...")
        _get_sv()._ensure_model()
    if "punc" in preload:
        logger.info("[Server] Loading PUNC...")
        _get_punc()._ensure_model()
    logger.info("[Server] All engines ready")

    logger.info(f"[Server] Starting on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
