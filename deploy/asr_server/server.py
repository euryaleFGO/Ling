#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ASR 服务器 - 统一的语音识别服务
包含：ASR、SER、SV、Diarization、PUNC、VAD

类似 TTS 服务器，提供 HTTP API 供客户端调用
支持流式识别和离线识别
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from flask import Flask, request, jsonify
import base64
import numpy as np
import io
import wave
import time
import threading
from typing import Optional, Dict, Any
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# 全局引擎实例（懒加载）
_asr_engine = None
_ser_engine = None
_sv_engine = None
_diarization_engine = None
_punc_engine = None
_vad_engine = None


def get_asr_engine():
    """获取 ASR 引擎（懒加载）"""
    global _asr_engine
    if _asr_engine is None:
        log.info("正在加载 ASR 引擎...")
        from backend.asr.asr_engine import ASREngine, ASRConfig
        config = ASRConfig()
        _asr_engine = ASREngine(config)
        log.info("ASR 引擎加载完成")
    return _asr_engine


def get_ser_engine():
    """获取 SER 引擎（懒加载）"""
    global _ser_engine
    if _ser_engine is None:
        log.info("正在加载 SER 引擎...")
        from core.ser_engine import SEREngine
        _ser_engine = SEREngine()
        log.info("SER 引擎加载完成")
    return _ser_engine


def get_sv_engine():
    """获取 SV 引擎（懒加载）"""
    global _sv_engine
    if _sv_engine is None:
        log.info("正在加载 SV 引擎...")
        from core.sv_engine import SVEngine
        _sv_engine = SVEngine()
        log.info("SV 引擎加载完成")
    return _sv_engine


def get_diarization_engine():
    """获取 Diarization 引擎（懒加载）"""
    global _diarization_engine
    if _diarization_engine is None:
        log.info("正在加载 Diarization 引擎...")
        from core.diarization_engine import DiarizationEngine
        from core.voiceprint_database import VoiceprintDatabase
        
        # 需要声纹数据库
        voiceprint_db = VoiceprintDatabase(project_root / "data" / "voiceprints")
        _diarization_engine = DiarizationEngine(
            sv_engine=get_sv_engine(),
            voiceprint_db=voiceprint_db
        )
        log.info("Diarization 引擎加载完成")
    return _diarization_engine


def get_punc_engine():
    """获取 PUNC 引擎（懒加载）"""
    global _punc_engine
    if _punc_engine is None:
        log.info("正在加载 PUNC 引擎...")
        from core.punc_engine import PuncEngine
        _punc_engine = PuncEngine()
        log.info("PUNC 引擎加载完成")
    return _punc_engine


def get_vad_engine():
    """获取 VAD 引擎（懒加载）"""
    global _vad_engine
    if _vad_engine is None:
        log.info("正在加载 VAD 引擎...")
        from core.vad import VAD
        _vad_engine = VAD()
        log.info("VAD 引擎加载完成")
    return _vad_engine


def wav_bytes_to_array(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """将 WAV 字节转换为 numpy 数组"""
    with io.BytesIO(wav_bytes) as f:
        with wave.open(f, 'rb') as wf:
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return audio, sample_rate


# ============================================================
# API 端点
# ============================================================

@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({"status": "ok", "service": "ASR Server"}), 200


@app.route('/asr/recognize', methods=['POST'])
def asr_recognize():
    """
    ASR 离线识别（整段音频）
    
    请求体：
    {
        "audio": "base64编码的WAV音频",
        "sample_rate": 16000,
        "language": "zh"
    }
    
    返回：
    {
        "status": "success",
        "text": "识别文本",
        "duration": 1.23
    }
    """
    try:
        data = request.json
        audio_b64 = data.get("audio")
        
        if not audio_b64:
            return jsonify({"status": "error", "error": "缺少 audio 参数"}), 400
        
        # 解码音频
        wav_bytes = base64.b64decode(audio_b64)
        audio, sample_rate = wav_bytes_to_array(wav_bytes)
        
        # 识别
        t_start = time.time()
        asr = get_asr_engine()
        text = asr.recognize_audio(audio, sample_rate)
        duration = time.time() - t_start
        
        log.info(f"[ASR] 识别完成: {text[:50]}... (耗时 {duration:.2f}s)")
        
        return jsonify({
            "status": "success",
            "text": text,
            "duration": duration
        }), 200
        
    except Exception as e:
        log.error(f"[ASR] 错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


# 流式识别会话管理
_stream_sessions = {}  # session_id -> {"cache": {}, "last_access": timestamp}
_session_lock = threading.Lock()


def cleanup_old_sessions():
    """清理超过 5 分钟未使用的会话"""
    current_time = time.time()
    with _session_lock:
        expired = [
            sid for sid, data in _stream_sessions.items()
            if current_time - data["last_access"] > 300
        ]
        for sid in expired:
            del _stream_sessions[sid]
            log.info(f"[ASR] 清理过期会话: {sid}")


@app.route('/asr/stream/start', methods=['POST'])
def asr_stream_start():
    """
    开始流式识别会话
    
    请求体：
    {
        "session_id": "unique_session_id"  # 可选，不提供则自动生成
    }
    
    返回：
    {
        "status": "success",
        "session_id": "session_123",
        "chunk_size": 9600  # 每次应发送的音频样本数
    }
    """
    try:
        import uuid
        
        data = request.json or {}
        session_id = data.get("session_id") or str(uuid.uuid4())
        
        # 清理旧会话
        cleanup_old_sessions()
        
        # 创建新会话
        with _session_lock:
            _stream_sessions[session_id] = {
                "cache": {},
                "last_access": time.time()
            }
        
        asr = get_asr_engine()
        chunk_size = asr.get_chunk_stride()
        
        log.info(f"[ASR] 开始流式会话: {session_id}")
        
        return jsonify({
            "status": "success",
            "session_id": session_id,
            "chunk_size": chunk_size
        }), 200
        
    except Exception as e:
        log.error(f"[ASR] 流式开始错误: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/asr/stream/feed', methods=['POST'])
def asr_stream_feed():
    """
    流式识别 - 输入音频块
    
    请求体：
    {
        "session_id": "session_123",
        "audio": "base64编码的音频数据（float32或int16）",
        "is_final": false  # 是否为最后一块
    }
    
    返回：
    {
        "status": "success",
        "text": "当前识别结果",
        "is_final": false
    }
    """
    try:
        data = request.json
        session_id = data.get("session_id")
        audio_b64 = data.get("audio")
        is_final = data.get("is_final", False)
        
        if not session_id:
            return jsonify({"status": "error", "error": "缺少 session_id"}), 400
        if not audio_b64:
            return jsonify({"status": "error", "error": "缺少 audio"}), 400
        
        # 获取会话
        with _session_lock:
            if session_id not in _stream_sessions:
                return jsonify({"status": "error", "error": "会话不存在"}), 404
            session = _stream_sessions[session_id]
            session["last_access"] = time.time()
            cache = session["cache"]
        
        # 解码音频
        audio_bytes = base64.b64decode(audio_b64)
        audio = np.frombuffer(audio_bytes, dtype=np.float32)
        
        # 流式识别
        asr = get_asr_engine()
        
        if is_final:
            # 最后一块，结束流式识别
            text = asr._model.generate(
                input=audio,
                cache=cache,
                is_final=True,
                chunk_size=asr.config.chunk_size,
                encoder_chunk_look_back=asr.config.encoder_chunk_look_back,
                decoder_chunk_look_back=asr.config.decoder_chunk_look_back,
            )
            
            # 清理会话
            with _session_lock:
                if session_id in _stream_sessions:
                    del _stream_sessions[session_id]
            
            result_text = text[0]["text"] if text and len(text) > 0 else ""
            log.info(f"[ASR] 流式识别完成: {session_id} -> {result_text[:50]}...")
        else:
            # 中间块
            text = asr._model.generate(
                input=audio,
                cache=cache,
                is_final=False,
                chunk_size=asr.config.chunk_size,
                encoder_chunk_look_back=asr.config.encoder_chunk_look_back,
                decoder_chunk_look_back=asr.config.decoder_chunk_look_back,
            )
            result_text = text[0]["text"] if text and len(text) > 0 else ""
        
        return jsonify({
            "status": "success",
            "text": result_text,
            "is_final": is_final
        }), 200
        
    except Exception as e:
        log.error(f"[ASR] 流式识别错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/asr/stream/cancel', methods=['POST'])
def asr_stream_cancel():
    """
    取消流式识别会话
    
    请求体：
    {
        "session_id": "session_123"
    }
    
    返回：
    {
        "status": "success"
    }
    """
    try:
        data = request.json
        session_id = data.get("session_id")
        
        if not session_id:
            return jsonify({"status": "error", "error": "缺少 session_id"}), 400
        
        # 删除会话
        with _session_lock:
            if session_id in _stream_sessions:
                del _stream_sessions[session_id]
                log.info(f"[ASR] 取消流式会话: {session_id}")
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        log.error(f"[ASR] 取消会话错误: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/ser/recognize', methods=['POST'])
def ser_recognize():
    """
    SER 情绪识别
    
    请求体：
    {
        "audio": "base64编码的WAV音频"
    }
    
    返回：
    {
        "status": "success",
        "emotion": "joy",
        "score": 0.95,
        "duration": 0.12
    }
    """
    try:
        data = request.json
        audio_b64 = data.get("audio")
        
        if not audio_b64:
            return jsonify({"status": "error", "error": "缺少 audio 参数"}), 400
        
        # 解码音频
        wav_bytes = base64.b64decode(audio_b64)
        audio, sample_rate = wav_bytes_to_array(wav_bytes)
        
        # 识别情绪
        t_start = time.time()
        ser = get_ser_engine()
        result = ser.recognize(audio, sample_rate)
        duration = time.time() - t_start
        
        log.info(f"[SER] 情绪识别: {result.label} (score={result.score:.2f}, 耗时 {duration:.2f}s)")
        
        return jsonify({
            "status": "success",
            "emotion": result.label,
            "score": result.score,
            "duration": duration
        }), 200
        
    except Exception as e:
        log.error(f"[SER] 错误: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/sv/extract', methods=['POST'])
def sv_extract():
    """
    SV 声纹提取
    
    请求体：
    {
        "audio": "base64编码的WAV音频"
    }
    
    返回：
    {
        "status": "success",
        "embedding": [0.1, 0.2, ...],  # 声纹向量
        "duration": 0.15
    }
    """
    try:
        data = request.json
        audio_b64 = data.get("audio")
        
        if not audio_b64:
            return jsonify({"status": "error", "error": "缺少 audio 参数"}), 400
        
        # 解码音频
        wav_bytes = base64.b64decode(audio_b64)
        audio, sample_rate = wav_bytes_to_array(wav_bytes)
        
        # 提取声纹
        t_start = time.time()
        sv = get_sv_engine()
        embedding = sv.embed(audio, sample_rate)
        duration = time.time() - t_start
        
        log.info(f"[SV] 声纹提取完成 (dim={len(embedding)}, 耗时 {duration:.2f}s)")
        
        return jsonify({
            "status": "success",
            "embedding": embedding.tolist(),
            "duration": duration
        }), 200
        
    except Exception as e:
        log.error(f"[SV] 错误: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/diarization/identify', methods=['POST'])
def diarization_identify():
    """
    说话人识别
    
    请求体：
    {
        "audio": "base64编码的WAV音频"
    }
    
    返回：
    {
        "status": "success",
        "speaker_id": "speaker_001",
        "score": 0.87,
        "duration": 0.18
    }
    """
    try:
        data = request.json
        audio_b64 = data.get("audio")
        
        if not audio_b64:
            return jsonify({"status": "error", "error": "缺少 audio 参数"}), 400
        
        # 解码音频
        wav_bytes = base64.b64decode(audio_b64)
        audio, sample_rate = wav_bytes_to_array(wav_bytes)
        
        # 识别说话人
        t_start = time.time()
        diarization = get_diarization_engine()
        result = diarization.identify(audio, sample_rate)
        duration = time.time() - t_start
        
        log.info(f"[Diarization] 说话人识别: {result.speaker_id} (score={result.score:.2f}, 耗时 {duration:.2f}s)")
        
        return jsonify({
            "status": "success",
            "speaker_id": result.speaker_id,
            "score": result.score,
            "reason": result.reason,
            "duration": duration
        }), 200
        
    except Exception as e:
        log.error(f"[Diarization] 错误: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/punc/restore', methods=['POST'])
def punc_restore():
    """
    标点恢复
    
    请求体：
    {
        "text": "你好我是小明今天天气真好"
    }
    
    返回：
    {
        "status": "success",
        "text": "你好，我是小明。今天天气真好。",
        "duration": 0.05
    }
    """
    try:
        data = request.json
        text = data.get("text")
        
        if not text:
            return jsonify({"status": "error", "error": "缺少 text 参数"}), 400
        
        # 恢复标点
        t_start = time.time()
        punc = get_punc_engine()
        result = punc.restore(text)
        duration = time.time() - t_start
        
        log.info(f"[PUNC] 标点恢复完成 (耗时 {duration:.2f}s)")
        
        return jsonify({
            "status": "success",
            "text": result,
            "duration": duration
        }), 200
        
    except Exception as e:
        log.error(f"[PUNC] 错误: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/vad/detect', methods=['POST'])
def vad_detect():
    """
    VAD 语音活动检测
    
    请求体：
    {
        "audio": "base64编码的WAV音频"
    }
    
    返回：
    {
        "status": "success",
        "has_speech": true,
        "segments": [[0.1, 1.5], [2.0, 3.5]],  # 语音段时间戳
        "duration": 0.03
    }
    """
    try:
        data = request.json
        audio_b64 = data.get("audio")
        
        if not audio_b64:
            return jsonify({"status": "error", "error": "缺少 audio 参数"}), 400
        
        # 解码音频
        wav_bytes = base64.b64decode(audio_b64)
        audio, sample_rate = wav_bytes_to_array(wav_bytes)
        
        # VAD 检测
        t_start = time.time()
        vad = get_vad_engine()
        # 注意：VAD 的具体 API 需要根据实际实现调整
        has_speech = vad.is_speech(audio)
        duration = time.time() - t_start
        
        log.info(f"[VAD] 检测完成: has_speech={has_speech} (耗时 {duration:.2f}s)")
        
        return jsonify({
            "status": "success",
            "has_speech": has_speech,
            "duration": duration
        }), 200
        
    except Exception as e:
        log.error(f"[VAD] 错误: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/all/process', methods=['POST'])
def all_process():
    """
    一站式处理：ASR + SER + Diarization + PUNC
    
    请求体：
    {
        "audio": "base64编码的WAV音频",
        "enable_ser": true,
        "enable_diarization": true,
        "enable_punc": true
    }
    
    返回：
    {
        "status": "success",
        "text": "识别文本",
        "text_with_punc": "识别文本。",
        "emotion": "joy",
        "emotion_score": 0.95,
        "speaker_id": "speaker_001",
        "speaker_score": 0.87,
        "duration": 1.5
    }
    """
    try:
        data = request.json
        audio_b64 = data.get("audio")
        enable_ser = data.get("enable_ser", False)
        enable_diarization = data.get("enable_diarization", False)
        enable_punc = data.get("enable_punc", False)
        
        if not audio_b64:
            return jsonify({"status": "error", "error": "缺少 audio 参数"}), 400
        
        # 解码音频
        wav_bytes = base64.b64decode(audio_b64)
        audio, sample_rate = wav_bytes_to_array(wav_bytes)
        
        t_start = time.time()
        result = {}
        
        # 1. ASR 识别
        asr = get_asr_engine()
        text = asr.recognize_audio(audio, sample_rate)
        result["text"] = text
        
        # 2. SER 情绪识别（可选）
        if enable_ser:
            ser = get_ser_engine()
            ser_result = ser.recognize(audio, sample_rate)
            result["emotion"] = ser_result.label
            result["emotion_score"] = ser_result.score
        
        # 3. Diarization 说话人识别（可选）
        if enable_diarization:
            diarization = get_diarization_engine()
            dia_result = diarization.identify(audio, sample_rate)
            result["speaker_id"] = dia_result.speaker_id
            result["speaker_score"] = dia_result.score
        
        # 4. PUNC 标点恢复（可选）
        if enable_punc and text:
            punc = get_punc_engine()
            text_with_punc = punc.restore(text)
            result["text_with_punc"] = text_with_punc
        
        duration = time.time() - t_start
        result["status"] = "success"
        result["duration"] = duration
        
        log.info(f"[ALL] 一站式处理完成 (耗时 {duration:.2f}s)")
        
        return jsonify(result), 200
        
    except Exception as e:
        log.error(f"[ALL] 错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='ASR 服务器')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址 (默认: 127.0.0.1，仅本地访问)')
    parser.add_argument('--port', type=int, default=5002, help='监听端口')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    
    args = parser.parse_args()
    
    log.info("=" * 60)
    log.info("ASR 服务器启动")
    log.info(f"监听地址: {args.host}:{args.port}")
    log.info("=" * 60)
    
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
