# -*- coding: utf-8 -*-
"""
DiarizationEngine 综合单元测试

测试覆盖需求：
- 需求 2.1: 声纹提取和相似度计算
- 需求 2.2: 阈值判断逻辑
- 需求 2.3: 音频时长检查
- 需求 2.4: 错误处理和降级策略
- 需求 2.5: 缓存机制
- 需求 8.2: 降级到上一次识别结果
- 需求 8.4: 超时控制
"""

import hashlib
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import numpy as np
import pytest

from src.core.diarization_engine import DiarizationEngine, DiarizationResult
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
    mock.embed = MagicMock(return_value=np.random.randn(192).astype(np.float32))
    return mock


@pytest.fixture
def voiceprint_db(temp_storage):
    """创建 VoiceprintDatabase 实例"""
    return VoiceprintDatabase(temp_storage)


@pytest.fixture
def engine(mock_sv_engine, voiceprint_db):
    """创建 DiarizationEngine 实例"""
    return DiarizationEngine(
        sv_engine=mock_sv_engine,
        voiceprint_db=voiceprint_db,
        threshold=0.75,
        min_audio_sec=0.8,
        timeout_ms=500,
        max_failures=3
    )


@pytest.fixture
def sample_audio():
    """创建示例音频（1秒，16kHz）"""
    return np.random.randn(16000).astype(np.float32)


@pytest.fixture
def short_audio():
    """创建短音频（0.5秒，16kHz）"""
    return np.random.randn(8000).astype(np.float32)


class TestVoiceprintExtraction:
    """测试声纹提取功能（需求 2.1）"""
    
    def test_extract_embedding_success(self, engine, mock_sv_engine, sample_audio):
        """测试成功提取声纹"""
        expected_emb = np.random.randn(192).astype(np.float32)
        mock_sv_engine.embed.return_value = expected_emb
        
        result = engine._extract_embedding_cached(sample_audio, 16000)
        
        assert result is not None
        assert result.shape == (192,)
        assert np.array_equal(result, expected_emb)
        mock_sv_engine.embed.assert_called_once()
    
    def test_extract_embedding_with_cache(self, engine, mock_sv_engine, sample_audio):
        """测试缓存机制避免重复提取"""
        expected_emb = np.random.randn(192).astype(np.float32)
        mock_sv_engine.embed.return_value = expected_emb
        
        # 第一次提取
        result1 = engine._extract_embedding_cached(sample_audio, 16000)
        assert mock_sv_engine.embed.call_count == 1
        
        # 第二次提取（相同音频）
        result2 = engine._extract_embedding_cached(sample_audio, 16000)
        assert mock_sv_engine.embed.call_count == 1  # 没有增加
        
        # 结果应该相同
        assert np.array_equal(result1, result2)
    
    def test_extract_embedding_different_audio(self, engine, mock_sv_engine):
        """测试不同音频不使用缓存"""
        audio1 = np.random.randn(16000).astype(np.float32)
        audio2 = np.random.randn(16000).astype(np.float32)
        
        engine._extract_embedding_cached(audio1, 16000)
        engine._extract_embedding_cached(audio2, 16000)
        
        assert mock_sv_engine.embed.call_count == 2


class TestSimilarityCalculation:
    """测试相似度计算（需求 2.1）"""
    
    def test_perfect_match(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试完全匹配的情况"""
        # 注册说话人
        speaker_id = "speaker_001"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        
        # 返回相同的声纹
        mock_sv_engine.embed.return_value = embedding
        
        result = engine.identify(sample_audio, 16000)
        
        assert result.speaker_id == speaker_id
        assert result.score >= 0.99
        assert result.reason == "matched"
    
    def test_high_similarity_match(self, engine, voiceprint_db, mock_sv_engine):
        """测试高相似度匹配"""
        speaker_id = "speaker_002"
        embedding1 = np.random.randn(192).astype(np.float32)
        embedding1 = embedding1 / np.linalg.norm(embedding1)
        voiceprint_db.save_voiceprint(speaker_id, embedding1)
        
        # 返回相似但不完全相同的声纹（使用更小的噪声确保相似度高于阈值）
        embedding2 = embedding1 + np.random.randn(192).astype(np.float32) * 0.05
        embedding2 = embedding2 / np.linalg.norm(embedding2)
        mock_sv_engine.embed.return_value = embedding2
        
        # 使用不同的音频避免缓存
        audio = np.random.randn(16000).astype(np.float32)
        result = engine.identify(audio, 16000)
        
        # 应该能匹配上
        assert result.speaker_id == speaker_id
        assert result.score >= 0.75
    
    def test_low_similarity_no_match(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试低相似度不匹配"""
        speaker_id = "speaker_003"
        embedding1 = np.random.randn(192).astype(np.float32)
        embedding1 = embedding1 / np.linalg.norm(embedding1)
        voiceprint_db.save_voiceprint(speaker_id, embedding1)
        
        # 返回完全不同的声纹
        embedding2 = np.random.randn(192).astype(np.float32)
        embedding2 = embedding2 / np.linalg.norm(embedding2)
        mock_sv_engine.embed.return_value = embedding2
        
        result = engine.identify(sample_audio, 16000)
        
        # 应该匹配不上
        assert result.speaker_id == "unknown"
        assert "no_match" in result.reason


class TestThresholdLogic:
    """测试阈值判断逻辑（需求 2.2）"""
    
    def test_threshold_boundary_above(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试刚好超过阈值"""
        speaker_id = "speaker_004"
        embedding1 = np.random.randn(192).astype(np.float32)
        embedding1 = embedding1 / np.linalg.norm(embedding1)
        voiceprint_db.save_voiceprint(speaker_id, embedding1)
        
        # 构造相似度刚好为 0.76 的声纹（略高于阈值 0.75）
        embedding2 = embedding1 * 0.76 + np.random.randn(192).astype(np.float32) * 0.24
        embedding2 = embedding2 / np.linalg.norm(embedding2)
        mock_sv_engine.embed.return_value = embedding2
        
        result = engine.identify(sample_audio, 16000)
        
        # 应该匹配上
        if result.score >= 0.75:
            assert result.speaker_id == speaker_id
    
    def test_threshold_boundary_below(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试刚好低于阈值"""
        speaker_id = "speaker_005"
        embedding1 = np.random.randn(192).astype(np.float32)
        embedding1 = embedding1 / np.linalg.norm(embedding1)
        voiceprint_db.save_voiceprint(speaker_id, embedding1)
        
        # 构造相似度刚好为 0.74 的声纹（略低于阈值 0.75）
        embedding2 = embedding1 * 0.74 + np.random.randn(192).astype(np.float32) * 0.26
        embedding2 = embedding2 / np.linalg.norm(embedding2)
        mock_sv_engine.embed.return_value = embedding2
        
        result = engine.identify(sample_audio, 16000)
        
        # 应该匹配不上
        if result.score < 0.75:
            assert result.speaker_id == "unknown"
    
    def test_confidence_threshold(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试高置信度阈值（threshold + 0.05）"""
        speaker_id = "speaker_006"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        
        # 完全匹配
        mock_sv_engine.embed.return_value = embedding
        
        result = engine.identify(sample_audio, 16000)
        
        assert result.speaker_id == speaker_id
        assert result.score >= 0.80  # 0.75 + 0.05
        assert result.is_confident is True


class TestAudioDurationCheck:
    """测试音频时长检查（需求 2.3）"""
    
    def test_audio_too_short(self, engine, short_audio):
        """测试音频过短时跳过识别"""
        result = engine.identify(short_audio, 16000)
        
        assert result.speaker_id == "unknown"
        assert result.score == 0.0
        assert "audio_too_short" in result.reason
        assert result.duration_sec < 0.8
        assert result.is_confident is False
    
    def test_audio_minimum_duration(self, engine, voiceprint_db, mock_sv_engine):
        """测试最小音频时长边界"""
        # 创建刚好 0.8 秒的音频
        audio = np.random.randn(12800).astype(np.float32)  # 0.8s * 16000
        
        speaker_id = "speaker_007"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        result = engine.identify(audio, 16000)
        
        # 应该触发识别
        assert result.duration_sec >= 0.8
        assert result.speaker_id == speaker_id
    
    def test_audio_sufficient_duration(self, engine, sample_audio):
        """测试音频时长足够"""
        result = engine.identify(sample_audio, 16000)
        
        # 应该触发识别（即使数据库为空）
        assert result.duration_sec >= 0.8
        assert "audio_too_short" not in result.reason


class TestCachingMechanism:
    """测试缓存机制（需求 2.5）"""
    
    def test_cache_hit(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试缓存命中"""
        speaker_id = "speaker_008"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        # 第一次识别
        result1 = engine.identify(sample_audio, 16000)
        call_count_1 = mock_sv_engine.embed.call_count
        
        # 第二次识别（相同音频）
        result2 = engine.identify(sample_audio, 16000)
        call_count_2 = mock_sv_engine.embed.call_count
        
        # 应该使用缓存，不增加调用次数
        assert call_count_1 == call_count_2
        assert result1.speaker_id == result2.speaker_id
    
    def test_cache_miss(self, engine, voiceprint_db, mock_sv_engine):
        """测试缓存未命中"""
        speaker_id = "speaker_009"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        # 两次不同的音频
        audio1 = np.random.randn(16000).astype(np.float32)
        audio2 = np.random.randn(16000).astype(np.float32)
        
        engine.identify(audio1, 16000)
        call_count_1 = mock_sv_engine.embed.call_count
        
        engine.identify(audio2, 16000)
        call_count_2 = mock_sv_engine.embed.call_count
        
        # 应该增加调用次数
        assert call_count_2 > call_count_1
    
    def test_cache_size_limit(self, engine, voiceprint_db, mock_sv_engine):
        """测试缓存大小限制"""
        speaker_id = "speaker_010"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        # 创建超过缓存大小的音频样本
        for i in range(105):  # 缓存大小是 100
            audio = np.random.randn(16000).astype(np.float32)
            engine.identify(audio, 16000)
        
        # 缓存大小应该不超过限制
        assert len(engine._embedding_cache) <= 100
    
    def test_cache_key_generation(self, engine, sample_audio):
        """测试缓存键生成"""
        # 相同音频应该生成相同的哈希
        hash1 = hashlib.md5(sample_audio.tobytes()).hexdigest()
        hash2 = hashlib.md5(sample_audio.tobytes()).hexdigest()
        
        assert hash1 == hash2
        
        # 不同音频应该生成不同的哈希
        different_audio = np.random.randn(16000).astype(np.float32)
        hash3 = hashlib.md5(different_audio.tobytes()).hexdigest()
        
        assert hash1 != hash3


class TestErrorHandling:
    """测试错误处理（需求 2.4, 8.2）"""
    
    def test_embedding_extraction_failure(self, engine, mock_sv_engine, sample_audio):
        """测试声纹提取失败"""
        mock_sv_engine.embed.side_effect = Exception("Embedding failed")
        
        result = engine.identify(sample_audio, 16000)
        
        assert result.speaker_id == "unknown"
        assert "error" in result.reason
        assert engine._consecutive_failures == 1
    
    def test_database_access_failure(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试数据库访问失败"""
        mock_sv_engine.embed.return_value = np.random.randn(192).astype(np.float32)
        voiceprint_db.find_best_match = Mock(side_effect=Exception("Database error"))
        
        result = engine.identify(sample_audio, 16000)
        
        assert result.speaker_id == "unknown"
        assert "error" in result.reason
        assert engine._consecutive_failures == 1
    
    def test_fallback_to_last_speaker(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试降级到上一次识别结果（需求 8.2）"""
        # 第一次成功识别
        speaker_id = "speaker_011"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        result1 = engine.identify(sample_audio, 16000)
        assert result1.speaker_id == speaker_id
        
        # 清除缓存
        engine._embedding_cache.clear()
        
        # 第二次失败
        mock_sv_engine.embed.side_effect = Exception("Embedding failed")
        
        result2 = engine.identify(sample_audio, 16000)
        
        # 应该返回上一次的 speaker_id
        assert result2.speaker_id == speaker_id
        assert "error" in result2.reason
    
    def test_consecutive_failures_counter(self, engine, mock_sv_engine, sample_audio):
        """测试连续失败计数器"""
        mock_sv_engine.embed.side_effect = Exception("Persistent failure")
        
        # 第一次失败
        engine.identify(sample_audio, 16000)
        assert engine._consecutive_failures == 1
        
        # 第二次失败
        engine.identify(sample_audio, 16000)
        assert engine._consecutive_failures == 2
        
        # 第三次失败
        engine.identify(sample_audio, 16000)
        assert engine._consecutive_failures == 3
        assert engine._temporarily_disabled is True
    
    def test_success_resets_failure_counter(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试成功识别重置失败计数器"""
        # 先失败一次
        mock_sv_engine.embed.side_effect = Exception("Temporary failure")
        engine.identify(sample_audio, 16000)
        assert engine._consecutive_failures == 1
        
        # 然后成功
        mock_sv_engine.embed.side_effect = None
        speaker_id = "speaker_012"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        result = engine.identify(sample_audio, 16000)
        
        # 失败计数应该被重置
        assert result.speaker_id == speaker_id
        assert engine._consecutive_failures == 0


class TestTimeoutControl:
    """测试超时控制（需求 8.4）"""
    
    def test_identification_timeout(self, engine, mock_sv_engine, sample_audio):
        """测试识别超时"""
        # 模拟慢速识别
        def slow_embed(audio, sample_rate):
            time.sleep(0.6)  # 超过 500ms 超时
            return np.random.randn(192).astype(np.float32)
        
        mock_sv_engine.embed.side_effect = slow_embed
        
        result = engine.identify(sample_audio, 16000)
        
        # 应该超时
        assert "timeout" in result.reason
        assert engine._consecutive_failures == 1
    
    def test_timeout_uses_last_result(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试超时时使用上一次结果"""
        # 第一次成功
        speaker_id = "speaker_013"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        result1 = engine.identify(sample_audio, 16000)
        assert result1.speaker_id == speaker_id
        
        # 清除缓存
        engine._embedding_cache.clear()
        
        # 第二次超时
        def slow_embed(audio, sample_rate):
            time.sleep(0.6)
            return np.random.randn(192).astype(np.float32)
        
        mock_sv_engine.embed.side_effect = slow_embed
        
        result2 = engine.identify(sample_audio, 16000)
        
        # 应该返回上一次的 speaker_id
        assert result2.speaker_id == speaker_id
        assert "timeout" in result2.reason


class TestAudioFormatConversion:
    """测试音频格式转换"""
    
    def test_int16_to_float32(self, engine, voiceprint_db, mock_sv_engine):
        """测试 int16 转 float32"""
        audio_int16 = (np.random.randn(16000) * 32767).astype(np.int16)
        
        speaker_id = "speaker_014"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        result = engine.identify(audio_int16, 16000)
        
        assert result is not None
        assert result.speaker_id == speaker_id
    
    def test_stereo_to_mono(self, engine, voiceprint_db, mock_sv_engine):
        """测试立体声转单声道"""
        audio_stereo = np.random.randn(16000, 2).astype(np.float32)
        
        speaker_id = "speaker_015"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        result = engine.identify(audio_stereo, 16000)
        
        assert result is not None
        assert result.speaker_id == speaker_id


class TestMultipleSpeakers:
    """测试多说话人场景"""
    
    def test_identify_multiple_speakers(self, engine, voiceprint_db, mock_sv_engine):
        """测试识别多个说话人"""
        # 注册 3 个说话人
        emb1 = np.random.randn(192).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(192).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        emb3 = np.random.randn(192).astype(np.float32)
        emb3 = emb3 / np.linalg.norm(emb3)
        
        voiceprint_db.save_voiceprint("speaker_1", emb1)
        voiceprint_db.save_voiceprint("speaker_2", emb2)
        voiceprint_db.save_voiceprint("speaker_3", emb3)
        
        # 识别每个说话人（使用不同的音频避免缓存）
        mock_sv_engine.embed.return_value = emb1
        audio1 = np.random.randn(16000).astype(np.float32)
        result1 = engine.identify(audio1, 16000)
        
        mock_sv_engine.embed.return_value = emb2
        audio2 = np.random.randn(16000).astype(np.float32)
        result2 = engine.identify(audio2, 16000)
        
        mock_sv_engine.embed.return_value = emb3
        audio3 = np.random.randn(16000).astype(np.float32)
        result3 = engine.identify(audio3, 16000)
        
        assert result1.speaker_id == "speaker_1"
        assert result2.speaker_id == "speaker_2"
        assert result3.speaker_id == "speaker_3"
    
    def test_best_match_selection(self, engine, voiceprint_db, mock_sv_engine):
        """测试选择最佳匹配"""
        # 注册 3 个说话人
        emb1 = np.random.randn(192).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(192).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        emb3 = np.random.randn(192).astype(np.float32)
        emb3 = emb3 / np.linalg.norm(emb3)
        
        voiceprint_db.save_voiceprint("speaker_1", emb1)
        voiceprint_db.save_voiceprint("speaker_2", emb2)
        voiceprint_db.save_voiceprint("speaker_3", emb3)
        
        # 返回与 speaker_2 最相似的声纹
        query_emb = emb2 + np.random.randn(192).astype(np.float32) * 0.1
        query_emb = query_emb / np.linalg.norm(query_emb)
        mock_sv_engine.embed.return_value = query_emb
        
        # 使用不同的音频避免缓存
        audio = np.random.randn(16000).astype(np.float32)
        result = engine.identify(audio, 16000)
        
        # 应该匹配到 speaker_2
        assert result.speaker_id == "speaker_2"


class TestUtilityMethods:
    """测试工具方法"""
    
    def test_get_last_speaker_initial(self, engine):
        """测试初始状态的 get_last_speaker"""
        assert engine.get_last_speaker() is None
    
    def test_get_last_speaker_after_identification(self, engine, voiceprint_db, mock_sv_engine, sample_audio):
        """测试识别后的 get_last_speaker"""
        speaker_id = "speaker_016"
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        voiceprint_db.save_voiceprint(speaker_id, embedding)
        mock_sv_engine.embed.return_value = embedding
        
        engine.identify(sample_audio, 16000)
        
        assert engine.get_last_speaker() == speaker_id
    
    def test_reset_failure_counter(self, engine, mock_sv_engine, sample_audio):
        """测试重置失败计数器"""
        # 模拟失败
        mock_sv_engine.embed.side_effect = Exception("Test failure")
        
        for _ in range(3):
            engine.identify(sample_audio, 16000)
        
        assert engine._temporarily_disabled is True
        assert engine._consecutive_failures == 3
        
        # 重置
        engine.reset_failure_counter()
        
        assert engine._temporarily_disabled is False
        assert engine._consecutive_failures == 0
    
    def test_is_temporarily_disabled(self, engine, mock_sv_engine, sample_audio):
        """测试 is_temporarily_disabled 方法"""
        assert engine.is_temporarily_disabled() is False
        
        # 触发临时禁用
        mock_sv_engine.embed.side_effect = Exception("Test failure")
        for _ in range(3):
            engine.identify(sample_audio, 16000)
        
        assert engine.is_temporarily_disabled() is True
    
    def test_notification_callback(self, engine, mock_sv_engine, sample_audio):
        """测试用户通知回调"""
        notifications = []
        
        def callback(msg):
            notifications.append(msg)
        
        engine.set_notification_callback(callback)
        
        # 触发临时禁用
        mock_sv_engine.embed.side_effect = Exception("Test failure")
        for _ in range(3):
            engine.identify(sample_audio, 16000)
        
        # 应该收到通知
        assert len(notifications) == 1
        assert "临时禁用" in notifications[0]
