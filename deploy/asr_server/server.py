#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ASR 服务器 - 自包含的语音识别服务

独立部署，不需要完整项目目录。
仅依赖: funasr, torch, flask, numpy

支持:
  - /asr/recognize       离线识别（整段音频）
  - /asr/stream/start    开始流式识别
  - /asr/stream/feed     流式输入音频块
  - /asr/stream/end      结束流式识别
  - /health              健康检查
"""

import os
import time
import uuid
import wave
import io
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import base64
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

# ---- 自动检测 GPU ----

def _detect_device() -> str:
    """自动检测可用设备"""
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda:0"
            name = torch.cuda.get_device_name(0)
            logging.info(f"[Device] GPU detected: {name}")
            return device
    except Exception:
        pass
    logging.info("[Device] Using CPU")
    return "cpu"


# ============================================================
#  ASR 引擎（自包含）
# ============================================================

@dataclass
class ASRConfig:
    """ASR 配置"""
    model_dir: str = None
    vad_model: str = None
    device: str = "cpu"
    disable_update: bool = True
    chunk_size: List[int] = field(default_factory=lambda: [0, 10, 5])
    encoder_chunk_look_back: int = 4
    decoder_chunk_look_back: int = 1
    sample_rate: int = 16000
    use_vad: bool = True
    suppress_progress: bool = True


class ASREngine:
    """自包含 ASR 引擎（基于 FunASR AutoModel）"""

    def __init__(self, config: ASRConfig = None):
        if config is None:
            config = ASRConfig()
        self.config = config
        self._model = None
        self._model_offline = None
        self._stream_cache = {}
        self._model_loaded = False

    def _find_model(self, name: str) -> str:
        """查找本地模型目录，找不到则返回模型名让 FunASR 自动下载"""
        search = [
            Path(__file__).parent / "models" / "ASR" / name,
            Path.home() / ".cache" / "modelscope" / "hub" / "models" / "iic" / name,
            Path.home() / ".cache" / "funasr" / name,
        ]
        for p in search:
            # 目录必须存在且包含模型文件（model.pt 或 config.yaml）
            if p.exists() and (p / "model.pt").exists():
                return str(p)
        return name  # 返回模型名，FunASR 会自动下载

    def _load_models(self):
        if self._model_loaded:
            return
        if not self.config.model_dir:
            self.config.model_dir = self._find_model("paraformer-zh-streaming")
        if not self.config.vad_model and self.config.use_vad:
            self.config.vad_model = self._find_model("fsmn-vad")

        from funasr import AutoModel
        logging.info(f"[ASR] Loading model: {self.config.model_dir} on {self.config.device}")

        self._model = AutoModel(
            model=self.config.model_dir,
            device=self.config.device,
            disable_update=self.config.disable_update,
        )
        self._model_loaded = True
        logging.info("[ASR] Model loaded")

    def _load_offline_model(self):
        if self._model_offline is not None:
            return
        from funasr import AutoModel
        kwargs = {
            "model": self.config.model_dir,
            "device": self.config.device,
            "disable_update": self.config.disable_update,
        }
        # 整段 HTTP 识别不要挂 vad_model：FunASR 在 inference_with_vad + CPU 分支会把
        # batch_size 置 0，触发 "batch_size must be set 1"（短音频、打断后尤其易现）。
        # 客户端已用本地 VAD 切段，此处直接对整段 wav 做离线推理即可。
        use_vad_offline = os.environ.get("ASR_OFFLINE_USE_VAD", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if use_vad_offline and self.config.use_vad and self.config.vad_model:
            kwargs["vad_model"] = self.config.vad_model
            kwargs["vad_kwargs"] = {"max_single_segment_time": 60000}
        self._model_offline = AutoModel(**kwargs)
        logging.info("[ASR] Offline model loaded (vad=%s)", use_vad_offline)

    def recognize_audio(self, audio: np.ndarray, sample_rate: int = 16000, hotwords: str = "") -> str:
        """离线识别整段音频"""
        self._load_models()
        self._load_offline_model()
        audio = self._normalize(audio)
        if audio.size == 0:
            return ""
        if sample_rate and sample_rate != self.config.sample_rate:
            import librosa
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=self.config.sample_rate)
        kwargs = {"input": audio}
        if hotwords:
            kwargs["hotword"] = hotwords
        res = self._model_offline.generate(**kwargs)
        if res and len(res) > 0 and "text" in res[0]:
            return res[0]["text"]
        return ""

    def get_chunk_stride(self) -> int:
        return self.config.chunk_size[1] * 960

    def start_stream(self):
        self._load_models()
        self._stream_cache = {}

    def feed_audio(self, chunk: np.ndarray) -> str:
        if not self._model_loaded:
            self._load_models()
        chunk = self._normalize(chunk)
        if chunk.size == 0:
            return ""
        res = self._model.generate(
            input=chunk, cache=self._stream_cache, is_final=False,
            chunk_size=self.config.chunk_size,
            encoder_chunk_look_back=self.config.encoder_chunk_look_back,
            decoder_chunk_look_back=self.config.decoder_chunk_look_back,
        )
        if res and len(res) > 0 and "text" in res[0]:
            return res[0]["text"]
        return ""

    def end_stream(self, chunk: np.ndarray = None) -> str:
        if chunk is None:
            chunk = np.zeros(16 * 60, dtype=np.float32)
        else:
            chunk = self._normalize(chunk)
            if chunk.size == 0:
                chunk = np.zeros(16 * 60, dtype=np.float32)
        res = self._model.generate(
            input=chunk, cache=self._stream_cache, is_final=True,
            chunk_size=self.config.chunk_size,
            encoder_chunk_look_back=self.config.encoder_chunk_look_back,
            decoder_chunk_look_back=self.config.decoder_chunk_look_back,
        )
        self._stream_cache = {}
        if res and len(res) > 0 and "text" in res[0]:
            return res[0]["text"]
        return ""

    @staticmethod
    def _normalize(audio: np.ndarray) -> np.ndarray:
        if audio is None or (isinstance(audio, np.ndarray) and audio.size == 0):
            return np.zeros(0, dtype=np.float32)
        if not isinstance(audio, np.ndarray):
            audio = np.asarray(audio)
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        max_val = float(np.max(np.abs(audio))) if audio.size else 0.0
        if max_val > 2.0:
            audio = audio / 32768.0
        return audio


# ============================================================
#  工具函数
# ============================================================

def wav_bytes_to_array(wav_bytes: bytes) -> tuple:
    """WAV 字节 -> numpy 数组"""
    with io.BytesIO(wav_bytes) as f:
        with wave.open(f, 'rb') as wf:
            sr = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return audio, sr


# ============================================================
#  Flask 应用
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# 全局引擎（懒加载）
_engine: Optional[ASREngine] = None


def get_engine() -> ASREngine:
    global _engine
    if _engine is None:
        device = os.environ.get("ASR_DEVICE", "auto")
        if device == "auto":
            device = _detect_device()
        logging.info(f"[ASR] 使用设备: {device} (环境变量 ASR_DEVICE={os.environ.get('ASR_DEVICE', '未设置')})")
        config = ASRConfig(device=device)
        _engine = ASREngine(config)
        # 预加载模型
        _engine._load_models()
    return _engine


# ---- 流式会话管理 ----

_stream_sessions: Dict[str, Dict] = {}
_session_lock = threading.Lock()


def _cleanup_sessions():
    now = time.time()
    with _session_lock:
        expired = [s for s, d in _stream_sessions.items() if now - d["last_access"] > 300]
        for s in expired:
            del _stream_sessions[s]


# ---- 端点 ----

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "ASR Server"}), 200


@app.route('/asr/recognize', methods=['POST'])
def asr_recognize():
    """离线识别"""
    try:
        data = request.json
        audio_b64 = data.get("audio")
        if not audio_b64:
            return jsonify({"status": "error", "error": "missing audio"}), 400

        wav_bytes = base64.b64decode(audio_b64)
        audio, sr = wav_bytes_to_array(wav_bytes)
        hotwords = data.get("hotwords", "")

        t0 = time.time()
        engine = get_engine()
        text = engine.recognize_audio(audio, sr, hotwords=hotwords)
        dt = time.time() - t0

        log.info(f"[ASR] {dt:.2f}s -> {text[:80]}")
        return jsonify({"status": "success", "text": text, "duration": dt}), 200
    except Exception as e:
        log.error(f"[ASR] error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/asr/stream/start', methods=['POST'])
def stream_start():
    """开始流式识别"""
    try:
        data = request.json or {}
        session_id = data.get("session_id") or str(uuid.uuid4())
        _cleanup_sessions()

        engine = get_engine()
        engine.start_stream()

        with _session_lock:
            _stream_sessions[session_id] = {"last_access": time.time()}

        return jsonify({
            "status": "success",
            "session_id": session_id,
            "chunk_size": engine.get_chunk_stride()
        }), 200
    except Exception as e:
        log.error(f"[Stream] start error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/asr/stream/feed', methods=['POST'])
def stream_feed():
    """流式输入音频块"""
    try:
        data = request.json
        session_id = data.get("session_id")
        audio_b64 = data.get("audio")

        if not session_id or not audio_b64:
            return jsonify({"status": "error", "error": "missing session_id or audio"}), 400

        with _session_lock:
            if session_id not in _stream_sessions:
                return jsonify({"status": "error", "error": "session not found"}), 404
            _stream_sessions[session_id]["last_access"] = time.time()

        audio_bytes = base64.b64decode(audio_b64)
        audio = np.frombuffer(audio_bytes, dtype=np.float32)

        engine = get_engine()
        text = engine.feed_audio(audio)

        return jsonify({"status": "success", "text": text, "is_final": False}), 200
    except Exception as e:
        log.error(f"[Stream] feed error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/asr/stream/end', methods=['POST'])
def stream_end():
    """结束流式识别"""
    try:
        data = request.json
        session_id = data.get("session_id")
        audio_b64 = data.get("audio")

        if not session_id:
            return jsonify({"status": "error", "error": "missing session_id"}), 400

        with _session_lock:
            if session_id in _stream_sessions:
                del _stream_sessions[session_id]

        engine = get_engine()
        chunk = None
        if audio_b64:
            audio_bytes = base64.b64decode(audio_b64)
            chunk = np.frombuffer(audio_bytes, dtype=np.float32)

        text = engine.end_stream(chunk)
        log.info(f"[Stream] ended: {session_id} -> {text[:80]}")
        return jsonify({"status": "success", "text": text, "is_final": True}), 200
    except Exception as e:
        log.error(f"[Stream] end error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/asr/stream/cancel', methods=['POST'])
def stream_cancel():
    """取消流式识别"""
    try:
        data = request.json
        session_id = data.get("session_id")
        if session_id:
            with _session_lock:
                _stream_sessions.pop(session_id, None)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='ASR Server')
    parser.add_argument('--host', default='0.0.0.0', help='Listen address (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5002, help='Listen port')
    parser.add_argument('--device', default='auto', help='Device: auto/cuda/cpu')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    if args.device != 'auto':
        os.environ['ASR_DEVICE'] = args.device

    log.info("=" * 60)
    log.info(f"ASR Server starting on {args.host}:{args.port}")
    log.info("=" * 60)
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
