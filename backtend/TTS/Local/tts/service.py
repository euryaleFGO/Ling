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
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# 设置路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 添加当前目录到 sys.path，方便导入 engine
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 设置 modelscope 缓存目录
os.environ.setdefault('MODELSCOPE_CACHE', os.path.expanduser('~/.cache/modelscope'))

# 导入 TTS 引擎
from engine import CosyvoiceRealTimeTTS

# 初始化 Flask 应用
app = Flask(__name__)
CORS(app)  # 允许跨域请求

# TTS 引擎
tts_engine = None
# 默认路径（可通过环境变量或配置文件修改）
DEFAULT_MODEL_PATH = os.getenv('COSYVOICE_MODEL_PATH', os.path.join(BASE_DIR, '..', '..', '..', '..', 'Model', 'CosyVoice2-0.5B'))
DEFAULT_REF_AUDIO = os.getenv('COSYVOICE_REF_AUDIO', os.path.join(BASE_DIR, '..', '..', '..', '..', 'Model', 'zjj.wav'))

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
        
        # 4GB 显卡强制关闭 JIT 和 TRT
        tts_engine = CosyvoiceRealTimeTTS(model_path, ref_audio, load_jit=False, load_trt=False)
        print("[TTS服务] TTS 引擎初始化成功")
        
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
        
        return jsonify({
            'status': 'success',
            'audio_url': audio_url,
            'audio': audio_b64,  # base64编码的音频数据
            'format': 'wav',
            'sample_rate': sample_rate,
            'filename': audio_filename
        })
        
    except Exception as e:
        print(f"[TTS服务] 生成音频失败：{e}")
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
    
    # 设置标准输出编码
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
    
    print("=" * 60)
    print("TTS 服务启动中...")
    print("=" * 60)
    
    # 可以从命令行参数获取模型路径
    model_path = sys.argv[1] if len(sys.argv) > 1 else None
    ref_audio = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 在主线程中初始化 TTS
    if not init_tts(model_path, ref_audio):
        print("[TTS服务] 警告：TTS 初始化失败，将在首次请求时重试")
    
    port = int(os.getenv('TTS_SERVICE_PORT', 5001))
    print(f"[TTS服务] 服务运行在 http://0.0.0.0:{port}")
    print(f"[TTS服务] 健康检查: http://localhost:{port}/health")
    print("=" * 60)
    
    # 运行服务（不使用 reloader，避免问题）
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True, use_reloader=False)

