#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立的 TTS 服务
基于 MagicMirror/backend/tts_service.py 的设计思路
提供独立的 HTTP 服务，接收文本并返回音频文件
"""
import os
import sys
import json
import base64
import time
import uuid
import threading
from queue import Queue, Empty
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS

# 设置路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # .../src/backend/tts
# 显式加入项目 src 路径，保证可以 import backend.*
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))  # .../src
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 兼容旧导入：把 tts 目录也加入，方便 from engine import ...
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 设置 modelscope 缓存目录
os.environ.setdefault('MODELSCOPE_CACHE', os.path.expanduser('~/.cache/modelscope'))

# 导入 TTS 引擎
from engine import CosyvoiceRealTimeTTS

# 初始化 Flask 应用
app = Flask(__name__)
CORS(app)  # 允许跨域请求

# -------------------- Rhubarb Lip Sync (Viseme 分析) --------------------
# Rhubarb 可执行文件路径：优先环境变量，其次同目录下的 rhubarb / rhubarb.exe
RHUBARB_PATH = os.getenv('RHUBARB_PATH', None)
if not RHUBARB_PATH:
    for _name in ('rhubarb.exe', 'rhubarb'):
        _candidate = os.path.join(BASE_DIR, _name)
        if os.path.isfile(_candidate):
            RHUBARB_PATH = _candidate
            break


def _analyze_visemes(wav_bytes: bytes, sample_rate: int) -> list | None:
    """
    调用 Rhubarb Lip Sync 对一段 WAV 进行视觉素（viseme）分析。
    返回: [{"start": 0.00, "end": 0.27, "value": "D"}, ...] 或 None
    """
    if not RHUBARB_PATH or not os.path.isfile(RHUBARB_PATH):
        return None

    import subprocess, tempfile
    tmp_wav = None
    tmp_json = None
    try:
        # 写入临时 WAV 文件
        tmp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        tmp_wav.write(wav_bytes)
        tmp_wav.close()

        tmp_json = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
        tmp_json.close()

        cmd = [
            RHUBARB_PATH,
            '-r', 'phonetic',       # 语言无关的音素识别（支持中文）
            '-f', 'json',           # JSON 输出格式
            '-o', tmp_json.name,
            '--quiet',
            tmp_wav.name,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"[Viseme] Rhubarb 分析失败: {result.stderr[:200]}")
            return None

        with open(tmp_json.name, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('mouthCues', [])
    except FileNotFoundError:
        print(f"[Viseme] Rhubarb 不可用: {RHUBARB_PATH}")
        return None
    except subprocess.TimeoutExpired:
        print("[Viseme] Rhubarb 分析超时")
        return None
    except Exception as e:
        print(f"[Viseme] 分析异常: {e}")
        return None
    finally:
        for p in (tmp_wav, tmp_json):
            if p and os.path.exists(p.name):
                try:
                    os.unlink(p.name)
                except OSError:
                    pass

if RHUBARB_PATH:
    print(f"[TTS服务] Rhubarb Lip Sync 已就绪: {RHUBARB_PATH}")
else:
    print("[TTS服务] Rhubarb 未找到，口型将 fallback 到 RMS 模式")
    print("  提示: 将 rhubarb(.exe) 放到 service.py 同目录，或设置 RHUBARB_PATH 环境变量")

# TTS 引擎
tts_engine = None
# 默认路径（可通过环境变量或配置文件修改）
DEFAULT_MODEL_PATH = os.getenv('COSYVOICE_MODEL_PATH', os.path.join(BASE_DIR, 'models', 'TTS', 'CosyVoice2-0.5B'))
DEFAULT_REF_AUDIO = os.getenv('COSYVOICE_REF_AUDIO', os.path.join(BASE_DIR, 'reference_audio', 'zjj.wav'))

def _should_use_trt(model_path: str) -> bool:
    """根据模型目录下是否存在 TRT plan 文件自动启用 TensorRT，环境变量可覆盖。"""
    trt_env = os.getenv("COSYVOICE_USE_TRT", "auto").strip().lower()
    if trt_env in ("0", "false", "no", "off"):
        return False

    plan_fp16 = os.path.join(model_path, "flow.decoder.estimator.fp16.mygpu.plan")
    plan_fp32 = os.path.join(model_path, "flow.decoder.estimator.fp32.mygpu.plan")
    has_plan = os.path.isfile(plan_fp16) or os.path.isfile(plan_fp32)

    if trt_env in ("1", "true", "yes", "on"):
        if has_plan:
            return True
        print("[TTS服务] COSYVOICE_USE_TRT=1 但未找到 .mygpu.plan 文件，TRT 未启用")
        return False

    # auto 模式：检测到 plan 自动启用，否则回退到 PyTorch
    return has_plan


def init_tts(model_path: str = None, ref_audio: str = None):
    """初始化 TTS 引擎（在主线程中）"""
    global tts_engine
    if tts_engine is not None:
        return True
    
    try:
        print("[TTS服务] 正在初始化 TTS 引擎...")
        
        # 使用提供的路径或默认路径
        model_path = model_path or DEFAULT_MODEL_PATH
        ref_audio = ref_audio or DEFAULT_REF_AUDIO
        
        if not os.path.exists(model_path):
            print(f"[TTS服务] 错误：模型路径不存在：{model_path}")
            return False
        
        if not os.path.exists(ref_audio):
            print(f"[TTS服务] 警告：参考音频不存在：{ref_audio}，将使用默认音色")
            ref_audio = None
        
        load_trt = _should_use_trt(model_path)
        tts_engine = CosyvoiceRealTimeTTS(model_path, ref_audio, load_jit=False, load_trt=load_trt)
        print("[TTS服务] TTS 引擎初始化成功" + (" (TensorRT 已启用)" if load_trt else ""))
        
        # 加载已保存的说话人信息（如果存在）
        spk2info_path = os.path.join(model_path, "spk2info.pt")
        if os.path.exists(spk2info_path):
            try:
                import torch
                tts_engine.cosyvoice.frontend.spk2info = torch.load(
                    spk2info_path,
                    map_location=tts_engine.cosyvoice.frontend.device
                )
                print(f"[TTS服务] 已加载 {len(tts_engine.cosyvoice.frontend.spk2info)} 个说话人")
            except Exception as e:
                print(f"[TTS服务] 警告：加载说话人信息失败：{e}")
        
        return True
    except Exception as e:
        print(f"[TTS服务] TTS 初始化失败：{e}")
        import traceback
        traceback.print_exc()
        return False


# -------------------- 队列/任务（云端常驻 + 客户端拉取）--------------------
# 设计：
# - 客户端先 POST /tts/enqueue 提交任务，拿到 job_id
# - 客户端随后循环 GET /tts/dequeue?job_id=... 拉取音频段（WAV bytes）
# - 服务端按“段”生成（尽快产出，近似流式），每段生成完就入队
_jobs_lock = threading.Lock()
_jobs: dict[str, dict] = {}  # job_id -> {'q': Queue, 'meta': dict}


def _ensure_tts_ready():
    global tts_engine
    if tts_engine is None:
        if not init_tts():
            raise RuntimeError("TTS引擎未初始化")


def _job_worker(job_id: str, text: str, use_clone: bool, spk_id: str | None):
    """后台任务：并行合成、按序推送，每段 WAV bytes 入队。"""
    try:
        _ensure_tts_ready()
        try:
            queue_workers = max(1, int(os.getenv("TTS_QUEUE_MAX_WORKERS", "2")))
        except Exception:
            queue_workers = 2

        produced = 0
        for audio_data, idx, total in tts_engine.generate_audio_streaming(
            text,
            use_clone=use_clone,
            max_workers=queue_workers,
            spk_id=spk_id,
        ):
            sr = tts_engine.sample_rate
            wav_bytes = tts_engine.audio_to_wav_bytes(audio_data, sr)

            # Rhubarb 视觉素分析（与 TTS 合成下一段并行执行）
            visemes = _analyze_visemes(wav_bytes, sr)

            with _jobs_lock:
                job = _jobs.get(job_id)
            if not job:
                return
            job["q"].put({"idx": idx, "total": total, "sr": sr, "wav": wav_bytes, "visemes": visemes}, block=True)
            produced += 1

        if produced == 0:
            raise RuntimeError("没有有效可合成文本")

        # 结束哨兵
        with _jobs_lock:
            job = _jobs.get(job_id)
        if job:
            job["q"].put(None, block=True)
            job["meta"]["done"] = True
    except Exception as e:
        with _jobs_lock:
            job = _jobs.get(job_id)
        if job:
            job["meta"]["error"] = str(e)
            job["meta"]["done"] = True
            job["q"].put(None, block=True)


@app.route('/tts/enqueue', methods=['POST'])
def tts_enqueue():
    """
    入队一个 TTS 任务，返回 job_id
    body:
      - text: str (required)
      - use_clone: bool (optional, default True)
      - spk_id: str (optional)
      - client_id: str (optional, 仅用于标记)
    """
    try:
        data = request.json or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "未提供文本内容"}), 400
        use_clone = bool(data.get("use_clone", True))
        spk_id = data.get("spk_id") or None
        client_id = data.get("client_id") or "default"

        job_id = uuid.uuid4().hex
        q: Queue = Queue()
        with _jobs_lock:
            _jobs[job_id] = {"q": q, "meta": {"client_id": client_id, "created": time.time(), "done": False, "error": None}}

        th = threading.Thread(target=_job_worker, args=(job_id, text, use_clone, spk_id), daemon=True)
        th.start()
        return jsonify({"status": "queued", "job_id": job_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/tts/dequeue', methods=['GET'])
def tts_dequeue():
    """
    拉取下一个音频段（WAV bytes）。
    query:
      - job_id: str (required)
      - timeout: float seconds (optional, default 20)
        返回：
            - 200: audio/wav（一个段）
            - 202: 暂无新段（任务仍在进行）
            - 204: 无内容（任务已完成且队列已空）
            - 404: job 不存在
            - 409: 任务失败（meta.error）
    """
    job_id = request.args.get("job_id", "").strip()
    if not job_id:
        return jsonify({"error": "缺少 job_id"}), 400
    timeout = float(request.args.get("timeout", 20))

    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "job 不存在"}), 404

    meta = job["meta"]
    if meta.get("error"):
        return jsonify({"error": meta["error"]}), 409

    try:
        item = job["q"].get(timeout=timeout)
    except Empty:
        # 暂无新段，但任务可能仍在进行，客户端应继续轮询
        return jsonify({"status": "waiting", "job_id": job_id, "done": bool(meta.get("done", False))}), 202

    if item is None:
        # done
        with _jobs_lock:
            _jobs.pop(job_id, None)
        return ("", 204)

    # 返回一个段的 wav bytes
    wav_bytes = item["wav"]
    sr = item["sr"]
    idx = item["idx"]
    total = item.get("total")
    visemes = item.get("visemes")
    from flask import Response
    resp = Response(wav_bytes, mimetype="audio/wav")
    resp.headers["X-Job-Id"] = job_id
    resp.headers["X-Segment-Idx"] = str(idx)
    # 附加 Viseme 数据（Base64 编码的 JSON 数组）
    if visemes:
        viseme_json = json.dumps(visemes, ensure_ascii=False, separators=(',', ':'))
        resp.headers["X-Viseme-Data"] = base64.b64encode(viseme_json.encode('utf-8')).decode('ascii')
    if total is not None:
        resp.headers["X-Segment-Total"] = str(total)
    resp.headers["X-Sample-Rate"] = str(sr)
    return resp

@app.route('/health', methods=['GET'])
def health():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'tts_initialized': tts_engine is not None
    })

@app.route('/tts/generate', methods=['POST'])
def generate_tts():
    """生成 TTS 音频"""
    global tts_engine
    
    if tts_engine is None:
        if not init_tts():
            return jsonify({'error': 'TTS引擎未初始化'}), 500
    
    try:
        data = request.json
        text = data.get('text', '')
        spk_id = data.get('spk_id', None)  # 可选的说话人ID
        use_clone = data.get('use_clone', True)
        
        if not text:
            return jsonify({'error': '未提供文本内容'}), 400
        
        print(f"[TTS服务] 收到请求：文本长度 {len(text)} 字符")
        
        # 生成音频
        if spk_id:
            result = tts_engine.generate_audio_with_speaker(text, spk_id)
        else:
            result = tts_engine.generate_audio(text, use_clone=use_clone)
        
        if result is None:
            return jsonify({'error': '音频生成失败'}), 500
        
        audio_data, sample_rate = result
        
        # 生成唯一文件名
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        audio_filename = f"tts_{timestamp}.wav"
        audio_dir = os.path.join(BASE_DIR, "audio_output")
        if not os.path.exists(audio_dir):
            os.makedirs(audio_dir, exist_ok=True)
        audio_path = os.path.join(audio_dir, audio_filename)
        
        # 保存音频文件
        tts_engine.audio_to_wav_file(audio_data, sample_rate, audio_path)
        
        # 生成文件URL
        audio_url = f"http://localhost:5001/audio/{audio_filename}"
        
        # 同时返回 base64 编码（可选）
        wav_bytes = tts_engine.audio_to_wav_bytes(audio_data, sample_rate)
        audio_b64 = base64.b64encode(wav_bytes).decode('utf-8')
        
        # Rhubarb 视觉素分析
        visemes = _analyze_visemes(wav_bytes, sample_rate)
        
        return jsonify({
            'status': 'success',
            'audio_url': audio_url,
            'audio': audio_b64,  # base64编码的音频数据
            'format': 'wav',
            'sample_rate': sample_rate,
            'filename': audio_filename,
            'visemes': visemes,  # 视觉素时间线（可能为 null）
        })
        
    except Exception as e:
        print(f"[TTS服务] 生成音频失败：{e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/tts/generate/stream', methods=['POST'])
def generate_tts_stream():
    """
    流式生成 TTS：按句/段边合成边返回，每段以 SSE 事件推送。
    body 同 /tts/generate：text, use_clone, spk_id。
    响应：text/event-stream，每段一个 event:
      event: segment
      data: {"idx":1,"total":3,"sr":16000,"wav_base64":"..."}
    """
    global tts_engine
    if tts_engine is None:
        if not init_tts():
            return jsonify({'error': 'TTS引擎未初始化'}), 500

    try:
        data = request.json or {}
        text = (data.get('text') or '').strip()
        use_clone = bool(data.get('use_clone', True))
        spk_id = data.get('spk_id') or None

        if not text:
            return jsonify({'error': '未提供文本内容'}), 400

        def event_stream():
            _ensure_tts_ready()
            for audio, idx, total in tts_engine.generate_audio_streaming(
                text, use_clone=use_clone, spk_id=spk_id
            ):
                wav_bytes = tts_engine.audio_to_wav_bytes(audio, tts_engine.sample_rate)
                b64 = base64.b64encode(wav_bytes).decode('utf-8')
                payload = json.dumps({
                    'idx': idx, 'total': total, 'sr': tts_engine.sample_rate,
                    'wav_base64': b64
                }, ensure_ascii=False)
                yield f"event: segment\ndata: {payload}\n\n"
            yield "event: done\ndata: {}\n\n"

        return Response(
            stream_with_context(event_stream()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            }
        )
    except Exception as e:
        print(f"[TTS服务] 流式生成失败：{e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/tts/add_speaker', methods=['POST'])
def add_speaker_tts():
    """在 TTS 服务中添加说话人"""
    global tts_engine
    
    if tts_engine is None:
        if not init_tts():
            return jsonify({'error': 'TTS引擎未初始化'}), 500
    
    try:
        # 接收音频文件和提示文本
        if 'audio' not in request.files:
            return jsonify({'error': '未提供音频文件'}), 400
        
        audio_file = request.files['audio']
        prompt_text = request.form.get('prompt_text', '').strip()
        spk_id = request.form.get('spk_id', None)  # 可选的说话人ID
        
        if not prompt_text:
            return jsonify({'error': '提示文本不能为空'}), 400
        
        # 保存临时音频文件
        import uuid
        temp_dir = os.path.join(BASE_DIR, 'temp_audio')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir, exist_ok=True)
        
        temp_filename = f"{uuid.uuid4()}.wav"
        temp_path = os.path.join(temp_dir, temp_filename)
        audio_file.save(temp_path)
        
        try:
            # 加载音频文件为 16k（使用 TTS 引擎的方法）
            prompt_speech_16k = tts_engine.load_wav_func(temp_path, 16000)
            
            # 如果没有提供 spk_id，生成一个
            if not spk_id:
                spk_id = f"spk_{uuid.uuid4().hex[:8]}"
            
            # 添加说话人到 TTS 引擎
            success = tts_engine.cosyvoice.add_zero_shot_spk(
                prompt_text=prompt_text,
                prompt_speech_16k=prompt_speech_16k,
                zero_shot_spk_id=spk_id
            )
            
            if success:
                # 保存说话人信息
                tts_engine.cosyvoice.save_spkinfo()
                return jsonify({
                    'status': 'success',
                    'spk_id': spk_id
                })
            else:
                return jsonify({'error': '添加说话人失败'}), 500
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
    except Exception as e:
        print(f"[TTS服务] 添加说话人失败：{e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/audio/<filename>')
def serve_audio(filename):
    """提供音频文件访问"""
    try:
        audio_dir = os.path.join(BASE_DIR, "audio_output")
        audio_path = os.path.join(audio_dir, filename)
        if not os.path.exists(audio_path):
            return jsonify({'error': '文件不存在'}), 404
        return send_from_directory(audio_dir, filename, mimetype='audio/wav')
    except Exception as e:
        print(f"[TTS服务] 提供音频文件失败: {e}")
        return jsonify({'error': '文件访问失败'}), 500

@app.route('/tts/speakers', methods=['GET'])
def list_speakers():
    """列出所有说话人"""
    global tts_engine
    
    if tts_engine is None:
        return jsonify({'speakers': []})
    
    try:
        if hasattr(tts_engine.cosyvoice, 'frontend') and hasattr(tts_engine.cosyvoice.frontend, 'spk2info'):
            speakers = list(tts_engine.cosyvoice.frontend.spk2info.keys())
            return jsonify({'speakers': speakers})
        return jsonify({'speakers': []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    import sys
    import argparse
    
    # 设置标准输出编码
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='TTS 服务')
    parser.add_argument('--host', default='0.0.0.0', help='服务地址')
    parser.add_argument('--port', type=int, default=5001, help='服务端口')
    parser.add_argument('--model', default=None, help='模型路径')
    parser.add_argument('--ref-audio', default=None, help='参考音频路径')
    args = parser.parse_args()
    
    print("=" * 60)
    print("TTS 服务启动中...")
    print("=" * 60)
    
    # 优先使用命令行参数，其次使用环境变量
    model_path = args.model or os.getenv('COSYVOICE_MODEL_PATH')
    ref_audio = args.ref_audio or os.getenv('COSYVOICE_REF_AUDIO')
    
    # 在主线程中初始化 TTS
    if not init_tts(model_path, ref_audio):
        print("[TTS服务] 警告：TTS 初始化失败，将在首次请求时重试")
    
    port = args.port or int(os.getenv('TTS_SERVICE_PORT', 5001))
    print(f"[TTS服务] 服务运行在 http://{args.host}:{port}")
    print(f"[TTS服务] 健康检查: http://localhost:{port}/health")
    print("=" * 60)
    
    # 运行服务（不使用 reloader，避免问题）
    app.run(debug=False, host=args.host, port=port, threaded=True, use_reloader=False)

