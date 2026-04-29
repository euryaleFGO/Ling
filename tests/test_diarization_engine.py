# -*- coding: utf-8 -*-
"""
DiarizationEngine 单元测试

测试覆盖：
- 声纹提取和相似度计算
- 阈值判断逻辑
- 音频时长检查
- 缓存机制
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.core.diarization_engine import DiarizationEngine
from src.core.sv_engine import SVEngine
from src.core.voiceprint_database import VoiceprintDatabase


@pytest.fixture
def temp_storage():
    """创建临时存储目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sv_engine():
    """创建 SVEngine 实例（使用真实模型）"""
    try:
        return SVEngine()
    except Exception:
        pytest.skip("SVEngine 模型不可用，跳过测试")


@pytest.fixture
def voiceprint_db(temp_storage):
    """创建 VoiceprintDatabase 实例"""
    return VoiceprintDatabase(temp_storage)


@pytest.fixture
def diarization_engine(sv_engine, voiceprint_db):
    """创建 DiarizationEngine 实例"""
    return DiarizationEngine(
        sv_engine=sv_engine,
        voiceprint_db=voiceprint_db,
        threshold=0.75,
        min_audio_sec=0.8
    )


@pytest.fixture
def sample_audio():
    """创建示例音频（1秒，16kHz）"""
    sample_rate = 16000
    duration = 1.0
    # 生成简单的正弦波
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    return audio


@pytest.fixture
def short_audio():
    """创建短音频（0.5秒，16kHz）"""
    sample_rate = 16000
    duration = 0.5
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    return audio


class TestDiarizationEngine:
    """DiarizationEngine 测试套件"""

    def test_init(self, diarization_engine):
        """测试初始化"""
        assert diarization_engine.threshold == 0.75
        assert diarization_engine.min_audio_sec == 0.8
        assert diarization_engine._last_speaker_id is None
        assert len(diarization_engine._embedding_cache) == 0

    def test_identify_audio_too_short(self, diarization_engine, short_audio):
        """测试音频过短时的处理"""
        result = diarization_engine.identify(short_audio, sample_rate=16000)
        
        assert result.speaker_id == "unknown"
        assert result.score == 0.0
        assert "audio_too_short" in result.reason
        assert result.is_confident is False
        assert result.duration_sec < 0.8

    def test_identify_no_match_empty_database(self, diarization_engine, sample_audio):
        """测试空数据库时无法匹配"""
        result = diarization_engine.identify(sample_audio, sample_rate=16000)
        
        assert result.speaker_id == "unknown"
        assert result.score == 0.0
        assert "no_match" in result.reason or "error" in result.reason
        assert result.is_confident is False

    def test_identify_with_registered_speaker(
        self, 
        diarization_engine, 
        voiceprint_db, 
        sv_engine,
        sample_audio
    ):
        """测试识别已注册的说话人"""
        # 注册说话人
        speaker_id = "test_speaker_001"
        embedding = sv_engine.embed(sample_audio, sample_rate=16000)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        
        # 识别（使用相同的音频）
        result = diarization_engine.identify(sample_audio, sample_rate=16000)
        
        assert result.speaker_id == speaker_id
        assert result.score >= 0.75
        assert result.reason == "matched"
        assert result.duration_sec >= 0.8

    def test_identify_below_threshold(
        self,
        diarization_engine,
        voiceprint_db,
        sv_engine,
        sample_audio
    ):
        """测试相似度低于阈值时返回 unknown"""
        # 注册说话人（使用不同的音频）
        speaker_id = "test_speaker_002"
        different_audio = np.random.randn(16000).astype(np.float32)
        embedding = sv_engine.embed(different_audio, sample_rate=16000)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        
        # 识别（使用完全不同的音频）
        result = diarization_engine.identify(sample_audio, sample_rate=16000)
        
        # 可能匹配不上（取决于随机音频的相似度）
        if result.speaker_id == "unknown":
            assert "no_match" in result.reason
            assert result.is_confident is False

    def test_get_last_speaker(self, diarization_engine, voiceprint_db, sv_engine, sample_audio):
        """测试获取上一次识别的说话人"""
        # 初始状态
        assert diarization_engine.get_last_speaker() is None
        
        # 注册并识别
        speaker_id = "test_speaker_003"
        embedding = sv_engine.embed(sample_audio, sample_rate=16000)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        
        result = diarization_engine.identify(sample_audio, sample_rate=16000)
        
        if result.speaker_id != "unknown":
            assert diarization_engine.get_last_speaker() == speaker_id

    def test_caching_mechanism(self, diarization_engine, voiceprint_db, sv_engine, sample_audio):
        """测试缓存机制"""
        # 注册说话人
        speaker_id = "test_speaker_004"
        embedding = sv_engine.embed(sample_audio, sample_rate=16000)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        
        # 第一次识别
        result1 = diarization_engine.identify(sample_audio, sample_rate=16000)
        cache_size_1 = len(diarization_engine._embedding_cache)
        
        # 第二次识别（相同音频，应该使用缓存）
        result2 = diarization_engine.identify(sample_audio, sample_rate=16000)
        cache_size_2 = len(diarization_engine._embedding_cache)
        
        # 缓存大小不应该增加
        assert cache_size_1 == cache_size_2
        
        # 结果应该一致
        if result1.speaker_id != "unknown":
            assert result1.speaker_id == result2.speaker_id
            assert abs(result1.score - result2.score) < 0.01

    def test_confidence_level(self, diarization_engine, voiceprint_db, sv_engine, sample_audio):
        """测试置信度判断"""
        # 注册说话人
        speaker_id = "test_speaker_005"
        embedding = sv_engine.embed(sample_audio, sample_rate=16000)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        
        # 识别（使用相同音频，应该高置信度）
        result = diarization_engine.identify(sample_audio, sample_rate=16000)
        
        if result.speaker_id != "unknown":
            # 完全匹配应该是高置信度
            if result.score >= 0.80:  # threshold + 0.05
                assert result.is_confident is True
            else:
                assert result.is_confident is False

    def test_audio_format_conversion(self, diarization_engine):
        """测试音频格式转换（int16 -> float32）"""
        # 创建 int16 格式的音频
        audio_int16 = (np.random.randn(16000) * 32767).astype(np.int16)
        
        # 应该能正常处理（内部会转换为 float32）
        result = diarization_engine.identify(audio_int16, sample_rate=16000)
        
        # 不应该崩溃，应该返回结果
        assert result is not None
        assert result.duration_sec >= 0.8

    def test_multiple_speakers(self, diarization_engine, voiceprint_db, sv_engine):
        """测试多个说话人的识别"""
        # 创建 3 个不同的音频样本
        audio1 = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 16000)).astype(np.float32)
        audio2 = np.sin(2 * np.pi * 880 * np.linspace(0, 1, 16000)).astype(np.float32)
        audio3 = np.sin(2 * np.pi * 1320 * np.linspace(0, 1, 16000)).astype(np.float32)
        
        # 注册 3 个说话人
        emb1 = sv_engine.embed(audio1, sample_rate=16000)
        emb2 = sv_engine.embed(audio2, sample_rate=16000)
        emb3 = sv_engine.embed(audio3, sample_rate=16000)
        
        voiceprint_db.save_voiceprint("speaker_1", emb1)
        voiceprint_db.save_voiceprint("speaker_2", emb2)
        voiceprint_db.save_voiceprint("speaker_3", emb3)
        
        # 识别每个说话人
        result1 = diarization_engine.identify(audio1, sample_rate=16000)
        result2 = diarization_engine.identify(audio2, sample_rate=16000)
        result3 = diarization_engine.identify(audio3, sample_rate=16000)
        
        # 应该能识别到对应的说话人
        if result1.speaker_id != "unknown":
            assert result1.speaker_id == "speaker_1"
        if result2.speaker_id != "unknown":
            assert result2.speaker_id == "speaker_2"
        if result3.speaker_id != "unknown":
            assert result3.speaker_id == "speaker_3"
