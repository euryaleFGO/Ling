# -*- coding: utf-8 -*-
"""
DiarizationEngine 基础单元测试（不依赖 FunASR 模型）

测试覆盖：
- 音频时长检查
- 缓存机制
- 基本逻辑验证
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

import numpy as np
import pytest

from src.core.diarization_engine import DiarizationEngine
from src.core.voiceprint_database import VoiceprintDatabase


@pytest.fixture
def temp_storage():
    """创建临时存储目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_sv_engine():
    """创建 Mock SVEngine"""
    mock = Mock()
    # 模拟 embed 方法返回固定的声纹向量
    mock.embed = MagicMock(return_value=np.random.randn(192).astype(np.float32))
    return mock


@pytest.fixture
def voiceprint_db(temp_storage):
    """创建 VoiceprintDatabase 实例"""
    return VoiceprintDatabase(temp_storage)


@pytest.fixture
def diarization_engine(mock_sv_engine, voiceprint_db):
    """创建 DiarizationEngine 实例（使用 Mock SVEngine）"""
    return DiarizationEngine(
        sv_engine=mock_sv_engine,
        voiceprint_db=voiceprint_db,
        threshold=0.75,
        min_audio_sec=0.8
    )


@pytest.fixture
def sample_audio():
    """创建示例音频（1秒，16kHz）"""
    sample_rate = 16000
    duration = 1.0
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


class TestDiarizationEngineBasic:
    """DiarizationEngine 基础测试套件"""

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
        assert "no_match" in result.reason
        assert result.is_confident is False

    def test_identify_with_registered_speaker(
        self, 
        diarization_engine, 
        voiceprint_db, 
        mock_sv_engine,
        sample_audio
    ):
        """测试识别已注册的说话人"""
        # 注册说话人（使用固定的声纹向量）
        speaker_id = "test_speaker_001"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)  # 归一化
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        
        # 配置 mock 返回相同的声纹向量
        mock_sv_engine.embed.return_value = embedding
        
        # 识别
        result = diarization_engine.identify(sample_audio, sample_rate=16000)
        
        assert result.speaker_id == speaker_id
        assert result.score >= 0.99  # 完全匹配
        assert result.reason == "matched"
        assert result.duration_sec >= 0.8
        assert result.is_confident is True

    def test_identify_below_threshold(
        self,
        diarization_engine,
        voiceprint_db,
        mock_sv_engine,
        sample_audio
    ):
        """测试相似度低于阈值时返回 unknown"""
        # 注册说话人
        speaker_id = "test_speaker_002"
        embedding1 = np.random.randn(192).astype(np.float32)
        embedding1 = embedding1 / np.linalg.norm(embedding1)
        voiceprint_db.save_voiceprint(speaker_id, embedding1)
        
        # 配置 mock 返回完全不同的声纹向量
        embedding2 = np.random.randn(192).astype(np.float32)
        embedding2 = embedding2 / np.linalg.norm(embedding2)
        mock_sv_engine.embed.return_value = embedding2
        
        # 识别
        result = diarization_engine.identify(sample_audio, sample_rate=16000)
        
        # 应该匹配不上（随机向量相似度很低）
        assert result.speaker_id == "unknown"
        assert "no_match" in result.reason
        assert result.is_confident is False

    def test_get_last_speaker(self, diarization_engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试获取上一次识别的说话人"""
        # 初始状态
        assert diarization_engine.get_last_speaker() is None
        
        # 注册并识别
        speaker_id = "test_speaker_003"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        result = diarization_engine.identify(sample_audio, sample_rate=16000)
        
        assert result.speaker_id == speaker_id
        assert diarization_engine.get_last_speaker() == speaker_id

    def test_caching_mechanism(self, diarization_engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试缓存机制"""
        # 注册说话人
        speaker_id = "test_speaker_004"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        # 第一次识别
        result1 = diarization_engine.identify(sample_audio, sample_rate=16000)
        assert mock_sv_engine.embed.call_count == 1
        
        # 第二次识别（相同音频，应该使用缓存）
        result2 = diarization_engine.identify(sample_audio, sample_rate=16000)
        assert mock_sv_engine.embed.call_count == 1  # 没有增加调用次数
        
        # 结果应该一致
        assert result1.speaker_id == result2.speaker_id
        assert result1.score == result2.score

    def test_confidence_level_high(self, diarization_engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试高置信度判断"""
        # 注册说话人
        speaker_id = "test_speaker_005"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        # 识别（完全匹配）
        result = diarization_engine.identify(sample_audio, sample_rate=16000)
        
        assert result.speaker_id == speaker_id
        assert result.score >= 0.80  # threshold + 0.05
        assert result.is_confident is True

    def test_confidence_level_low(self, diarization_engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试低置信度判断"""
        # 注册说话人
        speaker_id = "test_speaker_006"
        embedding1 = np.random.randn(192).astype(np.float32)
        embedding1 = embedding1 / np.linalg.norm(embedding1)
        voiceprint_db.save_voiceprint(speaker_id, embedding1)
        
        # 配置 mock 返回相似但不完全相同的声纹向量
        embedding2 = embedding1 + np.random.randn(192).astype(np.float32) * 0.3
        embedding2 = embedding2 / np.linalg.norm(embedding2)
        mock_sv_engine.embed.return_value = embedding2
        
        # 识别
        result = diarization_engine.identify(sample_audio, sample_rate=16000)
        
        # 可能匹配上但置信度不高
        if result.speaker_id == speaker_id:
            if result.score < 0.80:  # threshold + 0.05
                assert result.is_confident is False

    def test_audio_format_conversion_int16(self, diarization_engine, voiceprint_db, mock_sv_engine):
        """测试音频格式转换（int16 -> float32）"""
        # 创建 int16 格式的音频
        audio_int16 = (np.random.randn(16000) * 32767).astype(np.int16)
        
        # 注册说话人
        speaker_id = "test_speaker_007"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        # 应该能正常处理（内部会转换为 float32）
        result = diarization_engine.identify(audio_int16, sample_rate=16000)
        
        assert result is not None
        assert result.duration_sec >= 0.8
        assert result.speaker_id == speaker_id

    def test_audio_format_conversion_stereo(self, diarization_engine, voiceprint_db, mock_sv_engine):
        """测试音频格式转换（stereo -> mono）"""
        # 创建立体声音频
        audio_stereo = np.random.randn(16000, 2).astype(np.float32)
        
        # 注册说话人
        speaker_id = "test_speaker_008"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        # 应该能正常处理（内部会转换为 mono）
        result = diarization_engine.identify(audio_stereo, sample_rate=16000)
        
        assert result is not None
        assert result.duration_sec >= 0.8
        assert result.speaker_id == speaker_id

    def test_multiple_speakers(self, diarization_engine, voiceprint_db, mock_sv_engine):
        """测试多个说话人的识别"""
        # 创建 3 个不同的声纹向量
        emb1 = np.random.randn(192).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(192).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        emb3 = np.random.randn(192).astype(np.float32)
        emb3 = emb3 / np.linalg.norm(emb3)
        
        # 注册 3 个说话人
        voiceprint_db.save_voiceprint("speaker_1", emb1)
        voiceprint_db.save_voiceprint("speaker_2", emb2)
        voiceprint_db.save_voiceprint("speaker_3", emb3)
        
        # 创建测试音频
        audio = np.random.randn(16000).astype(np.float32)
        
        # 识别每个说话人
        mock_sv_engine.embed.return_value = emb1
        result1 = diarization_engine.identify(audio, sample_rate=16000)
        
        mock_sv_engine.embed.return_value = emb2
        result2 = diarization_engine.identify(audio, sample_rate=16000)
        
        mock_sv_engine.embed.return_value = emb3
        result3 = diarization_engine.identify(audio, sample_rate=16000)
        
        # 应该能识别到对应的说话人
        assert result1.speaker_id == "speaker_1"
        assert result2.speaker_id == "speaker_2"
        assert result3.speaker_id == "speaker_3"

    def test_cache_size_limit(self, diarization_engine, voiceprint_db, mock_sv_engine):
        """测试缓存大小限制"""
        # 注册说话人
        speaker_id = "test_speaker_009"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        # 创建超过缓存大小的音频样本
        for i in range(105):  # 缓存大小是 100
            audio = np.random.randn(16000).astype(np.float32)
            diarization_engine.identify(audio, sample_rate=16000)
        
        # 缓存大小应该不超过限制
        assert len(diarization_engine._embedding_cache) <= 100
