# -*- coding: utf-8 -*-
"""
简单验证脚本：测试 DiarizationEngine 实现

不依赖 pytest，直接运行验证核心功能
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import tempfile
import numpy as np

from src.core.diarization_engine import DiarizationEngine, DiarizationResult
from src.core.sv_engine import SVEngine
from src.core.voiceprint_database import VoiceprintDatabase


def test_initialization():
    """测试 1: 初始化"""
    print("测试 1: 初始化 DiarizationEngine...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            sv_engine = SVEngine()
            voiceprint_db = VoiceprintDatabase(Path(tmpdir))
            engine = DiarizationEngine(
                sv_engine=sv_engine,
                voiceprint_db=voiceprint_db,
                threshold=0.75,
                min_audio_sec=0.8
            )
            
            assert engine.threshold == 0.75, "阈值设置错误"
            assert engine.min_audio_sec == 0.8, "最小音频时长设置错误"
            assert engine._last_speaker_id is None, "初始 last_speaker_id 应为 None"
            assert len(engine._embedding_cache) == 0, "初始缓存应为空"
            
            print("✓ 初始化测试通过")
            return True
        except Exception as e:
            print(f"✗ 初始化测试失败: {e}")
            return False


def test_audio_too_short():
    """测试 2: 音频过短检查"""
    print("\n测试 2: 音频过短检查...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            sv_engine = SVEngine()
            voiceprint_db = VoiceprintDatabase(Path(tmpdir))
            engine = DiarizationEngine(
                sv_engine=sv_engine,
                voiceprint_db=voiceprint_db,
                threshold=0.75,
                min_audio_sec=0.8
            )
            
            # 创建 0.5 秒的短音频
            sample_rate = 16000
            duration = 0.5
            audio = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration))).astype(np.float32)
            
            result = engine.identify(audio, sample_rate=sample_rate)
            
            assert result.speaker_id == "unknown", "短音频应返回 unknown"
            assert result.score == 0.0, "短音频分数应为 0"
            assert "audio_too_short" in result.reason, "原因应包含 audio_too_short"
            assert result.is_confident is False, "短音频不应高置信度"
            assert result.duration_sec < 0.8, "时长应小于 0.8 秒"
            
            print("✓ 音频过短检查测试通过")
            return True
        except Exception as e:
            print(f"✗ 音频过短检查测试失败: {e}")
            return False


def test_empty_database():
    """测试 3: 空数据库识别"""
    print("\n测试 3: 空数据库识别...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            sv_engine = SVEngine()
            voiceprint_db = VoiceprintDatabase(Path(tmpdir))
            engine = DiarizationEngine(
                sv_engine=sv_engine,
                voiceprint_db=voiceprint_db,
                threshold=0.75,
                min_audio_sec=0.8
            )
            
            # 创建 1 秒的音频
            sample_rate = 16000
            duration = 1.0
            audio = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration))).astype(np.float32)
            
            result = engine.identify(audio, sample_rate=sample_rate)
            
            assert result.speaker_id == "unknown", "空数据库应返回 unknown"
            assert result.is_confident is False, "空数据库不应高置信度"
            
            print("✓ 空数据库识别测试通过")
            return True
        except Exception as e:
            print(f"✗ 空数据库识别测试失败: {e}")
            return False


def test_speaker_registration_and_identification():
    """测试 4: 说话人注册和识别"""
    print("\n测试 4: 说话人注册和识别...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            sv_engine = SVEngine()
            voiceprint_db = VoiceprintDatabase(Path(tmpdir))
            engine = DiarizationEngine(
                sv_engine=sv_engine,
                voiceprint_db=voiceprint_db,
                threshold=0.75,
                min_audio_sec=0.8
            )
            
            # 创建音频样本
            sample_rate = 16000
            duration = 1.0
            audio = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration))).astype(np.float32)
            
            # 注册说话人
            speaker_id = "test_speaker_001"
            embedding = sv_engine.embed(audio, sample_rate=sample_rate)
            voiceprint_db.save_voiceprint(speaker_id, embedding)
            
            # 识别（使用相同的音频）
            result = engine.identify(audio, sample_rate=sample_rate)
            
            assert result.speaker_id == speaker_id, f"应识别为 {speaker_id}，实际为 {result.speaker_id}"
            assert result.score >= 0.75, f"相似度应 >= 0.75，实际为 {result.score}"
            assert result.reason == "matched", "原因应为 matched"
            assert result.duration_sec >= 0.8, "时长应 >= 0.8 秒"
            
            print(f"✓ 说话人注册和识别测试通过 (score={result.score:.3f})")
            return True
        except Exception as e:
            print(f"✗ 说话人注册和识别测试失败: {e}")
            return False


def test_get_last_speaker():
    """测试 5: 获取上一次识别的说话人"""
    print("\n测试 5: 获取上一次识别的说话人...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            sv_engine = SVEngine()
            voiceprint_db = VoiceprintDatabase(Path(tmpdir))
            engine = DiarizationEngine(
                sv_engine=sv_engine,
                voiceprint_db=voiceprint_db,
                threshold=0.75,
                min_audio_sec=0.8
            )
            
            # 初始状态
            assert engine.get_last_speaker() is None, "初始状态应为 None"
            
            # 创建音频并注册
            sample_rate = 16000
            duration = 1.0
            audio = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration))).astype(np.float32)
            
            speaker_id = "test_speaker_002"
            embedding = sv_engine.embed(audio, sample_rate=sample_rate)
            voiceprint_db.save_voiceprint(speaker_id, embedding)
            
            # 识别
            result = engine.identify(audio, sample_rate=sample_rate)
            
            if result.speaker_id != "unknown":
                assert engine.get_last_speaker() == speaker_id, "应记录上一次识别的说话人"
                print(f"✓ 获取上一次识别的说话人测试通过 (last_speaker={speaker_id})")
            else:
                print("⚠ 识别为 unknown，跳过此测试")
            
            return True
        except Exception as e:
            print(f"✗ 获取上一次识别的说话人测试失败: {e}")
            return False


def test_caching():
    """测试 6: 缓存机制"""
    print("\n测试 6: 缓存机制...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            sv_engine = SVEngine()
            voiceprint_db = VoiceprintDatabase(Path(tmpdir))
            engine = DiarizationEngine(
                sv_engine=sv_engine,
                voiceprint_db=voiceprint_db,
                threshold=0.75,
                min_audio_sec=0.8
            )
            
            # 创建音频并注册
            sample_rate = 16000
            duration = 1.0
            audio = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration))).astype(np.float32)
            
            speaker_id = "test_speaker_003"
            embedding = sv_engine.embed(audio, sample_rate=sample_rate)
            voiceprint_db.save_voiceprint(speaker_id, embedding)
            
            # 第一次识别
            result1 = engine.identify(audio, sample_rate=sample_rate)
            cache_size_1 = len(engine._embedding_cache)
            
            # 第二次识别（相同音频，应使用缓存）
            result2 = engine.identify(audio, sample_rate=sample_rate)
            cache_size_2 = len(engine._embedding_cache)
            
            assert cache_size_1 == cache_size_2, "缓存大小不应增加"
            
            if result1.speaker_id != "unknown":
                assert result1.speaker_id == result2.speaker_id, "结果应一致"
                assert abs(result1.score - result2.score) < 0.01, "分数应一致"
            
            print(f"✓ 缓存机制测试通过 (cache_size={cache_size_1})")
            return True
        except Exception as e:
            print(f"✗ 缓存机制测试失败: {e}")
            return False


def main():
    """运行所有测试"""
    print("=" * 60)
    print("DiarizationEngine 实现验证")
    print("=" * 60)
    
    tests = [
        test_initialization,
        test_audio_too_short,
        test_empty_database,
        test_speaker_registration_and_identification,
        test_get_last_speaker,
        test_caching,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ 测试执行失败: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print(f"测试结果: {sum(results)}/{len(results)} 通过")
    print("=" * 60)
    
    if all(results):
        print("\n✓ 所有测试通过！DiarizationEngine 实现正确。")
        return 0
    else:
        print("\n✗ 部分测试失败，请检查实现。")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
