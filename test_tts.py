#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TTS 模块测试脚本
测试 CosyVoice2 TTS 是否能正常生成语音
"""
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.absolute()
backtend_path = project_root / "backtend"
if str(backtend_path) not in sys.path:
    sys.path.insert(0, str(backtend_path))

# TTS 模块路径
tts_module_path = project_root / "backtend" / "TTS" / "Local" / "tts"
if str(tts_module_path) not in sys.path:
    sys.path.insert(0, str(tts_module_path))

# Matcha-TTS 路径（cosyvoice 需要它）
matcha_tts_path = project_root / "backtend" / "TTS" / "Local" / "tts" / "third_party" / "Matcha-TTS"
if str(matcha_tts_path) not in sys.path:
    sys.path.insert(0, str(matcha_tts_path))

def test_environment():
    """测试环境配置"""
    print("=" * 60)
    print("环境检查")
    print("=" * 60)
    
    # Python 版本
    print(f"Python 版本: {sys.version}")
    print()
    
    # PyTorch 检查
    try:
        import torch
        print(f"✅ PyTorch 版本: {torch.__version__}")
        print(f"   CUDA 可用: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"   CUDA 版本: {torch.version.cuda}")
            print(f"   GPU 设备数量: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"   GPU {i}: {torch.cuda.get_device_name(i)}")
        else:
            print("   ⚠️  CUDA 不可用，将使用 CPU（会很慢）")
        print()
    except ImportError:
        print("❌ PyTorch 未安装")
        print()
        return False
    
    # NumPy 检查
    try:
        import numpy as np
        print(f"✅ NumPy 版本: {np.__version__}")
        print()
    except ImportError:
        print("❌ NumPy 未安装")
        print()
        return False
    
    # ONNX Runtime 检查
    try:
        import onnxruntime as ort
        print(f"✅ ONNX Runtime 版本: {ort.__version__}")
        providers = ort.get_available_providers()
        print(f"   可用后端: {providers}")
        if 'CUDAExecutionProvider' in providers:
            print("   ✅ CUDA 执行提供者可用")
        else:
            print("   ⚠️  CUDA 执行提供者不可用")
        print()
    except ImportError:
        print("❌ ONNX Runtime 未安装")
        print()
        return False
    
    # 其他依赖检查
    try:
        import librosa
        print(f"✅ librosa 版本: {librosa.__version__}")
    except ImportError:
        print("⚠️  librosa 未安装（可选）")
    
    try:
        import soundfile
        print(f"✅ soundfile 已安装")
    except ImportError:
        print("⚠️  soundfile 未安装（可选）")
    
    print()
    return True

def test_tts_import():
    """测试 TTS 模块导入"""
    print("=" * 60)
    print("TTS 模块导入测试")
    print("=" * 60)
    
    try:
        from engine import CosyvoiceRealTimeTTS  # type: ignore
        print("✅ TTS 引擎模块导入成功")
        print()
        return True
    except ImportError as e:
        print(f"❌ TTS 引擎模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False

def test_tts_initialization():
    """测试 TTS 引擎初始化"""
    print("=" * 60)
    print("TTS 引擎初始化测试")
    print("=" * 60)
    
    # 查找模型路径
    model_path = project_root / "backtend" / "models" / "TTS" / "CosyVoice2-0.5B"
    
    if not model_path.exists():
        print(f"❌ 模型路径不存在: {model_path}")
        print("   请确保模型已下载到正确位置")
        print()
        return None
    
    print(f"模型路径: {model_path}")
    
    # 查找参考音频
    ref_audio = None
    possible_ref_audios = [
        project_root / "backtend" / "TTS" / "Local" / "MagicMirror" / "backend" / "audio" / "zjj.wav",
        project_root / "Model" / "zjj.wav",
        project_root / "audio" / "zjj.wav",
    ]
    
    for audio_path in possible_ref_audios:
        if audio_path.exists():
            ref_audio = audio_path
            break
    
    if ref_audio:
        print(f"参考音频: {ref_audio}")
    else:
        print("⚠️  未找到参考音频，将使用默认音色")
    
    print()
    print("正在初始化 TTS 引擎（这可能需要一些时间）...")
    
    try:
        from engine import CosyvoiceRealTimeTTS  # type: ignore
        tts = CosyvoiceRealTimeTTS(
            str(model_path),
            str(ref_audio) if ref_audio else None
        )
        print("✅ TTS 引擎初始化成功")
        print()
        return tts
    except Exception as e:
        print(f"❌ TTS 引擎初始化失败: {e}")
        import traceback
        traceback.print_exc()
        print()
        return None

def test_tts_generation(tts):
    """测试 TTS 语音生成"""
    print("=" * 60)
    print("TTS 语音生成测试")
    print("=" * 60)
    
    test_text = "你好，这是一个语音合成测试。"
    print(f"测试文本: {test_text}")
    print()
    
    print("正在生成语音（这可能需要一些时间）...")
    
    try:
        result = tts.generate_audio(test_text, use_clone=True)
        
        if result:
            audio_data, sample_rate = result
            duration = len(audio_data) / sample_rate
            print(f"✅ 语音生成成功！")
            print(f"   采样率: {sample_rate} Hz")
            print(f"   时长: {duration:.2f} 秒")
            print(f"   音频数据形状: {audio_data.shape}")
            print()
            
            # 保存音频文件
            audio_dir = project_root / "audio_output"
            audio_dir.mkdir(exist_ok=True)
            
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_file = audio_dir / f"test_tts_{timestamp}.wav"
            
            tts.audio_to_wav_file(audio_data, sample_rate, str(audio_file))
            print(f"✅ 音频已保存: {audio_file}")
            print()
            return True
        else:
            print("❌ 语音生成返回 None")
            print()
            return False
            
    except Exception as e:
        print(f"❌ 语音生成失败: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False

def main():
    """主测试流程"""
    print()
    print("=" * 60)
    print("TTS 模块测试")
    print("=" * 60)
    print()
    
    # 1. 环境检查
    if not test_environment():
        print("❌ 环境检查失败，请先安装必要的依赖")
        return 1
    
    # 2. TTS 模块导入测试
    if not test_tts_import():
        print("❌ TTS 模块导入失败")
        return 1
    
    # 3. TTS 引擎初始化
    tts = test_tts_initialization()
    if tts is None:
        print("❌ TTS 引擎初始化失败")
        return 1
    
    # 4. TTS 语音生成测试
    if not test_tts_generation(tts):
        print("❌ TTS 语音生成失败")
        return 1
    
    print("=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
    print()
    return 0

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n用户中断测试")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

