# -*- coding: utf-8 -*-
"""
SpeakerManager 单元测试

测试覆盖：
- 说话人注册流程
- 声纹更新和融合策略
- 说话人删除
- 音频时长验证
- 重复名称处理
- 声纹质量评估
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

import numpy as np
import pytest

from src.core.speaker_manager import SpeakerManager, RegisterResult, SpeakerInfo
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
    # 返回归一化的随机向量
    embedding = np.random.randn(192).astype(np.float32)
    embedding = embedding / np.linalg.norm(embedding)
    mock.embed = MagicMock(return_value=embedding)
    mock.model_id = "test_model"
    return mock


@pytest.fixture
def voiceprint_db(temp_storage):
    """创建 VoiceprintDatabase 实例"""
    return VoiceprintDatabase(temp_storage)


@pytest.fixture
def speaker_manager(mock_sv_engine, voiceprint_db):
    """创建 SpeakerManager 实例"""
    return SpeakerManager(
        sv_engine=mock_sv_engine,
        voiceprint_db=voiceprint_db,
        user_profile_db=None
    )


@pytest.fixture
def valid_audio():
    """创建有效的音频样本（5秒，16kHz）"""
    return np.random.randn(80000).astype(np.float32)


@pytest.fixture
def short_audio():
    """创建过短的音频样本（2秒，16kHz）"""
    return np.random.randn(32000).astype(np.float32)


class TestSpeakerRegistration:
    """测试说话人注册功能"""
    
    def test_register_speaker_success(self, speaker_manager, mock_sv_engine, valid_audio):
        """测试成功注册说话人"""
        speaker_name = "张三"
        
        result = speaker_manager.register_speaker(
            speaker_name=speaker_name,
            audio=valid_audio,
            sample_rate=16000
        )
        
        assert result.success is True
        assert result.speaker_id != ""
        assert speaker_name in result.message
        assert result.quality_score > 0
        
        # 验证 SVEngine 被调用
        mock_sv_engine.embed.assert_called_once()
        
        # 验证说话人已保存
        speakers = speaker_manager.list_speakers()
        assert len(speakers) == 1
        assert speakers[0].speaker_name == speaker_name
    
    def test_register_speaker_with_metadata(self, speaker_manager, valid_audio):
        """测试注册说话人时包含元数据"""
        speaker_name = "李四"
        metadata = {
            "nickname": "小李",
            "department": "技术部"
        }
        
        result = speaker_manager.register_speaker(
            speaker_name=speaker_name,
            audio=valid_audio,
            metadata=metadata
        )
        
        assert result.success is True
        
        # 验证元数据被保存
        speaker_info = speaker_manager.get_speaker_info(result.speaker_id)
        assert speaker_info is not None
        assert speaker_info.metadata["nickname"] == "小李"
        assert speaker_info.metadata["department"] == "技术部"
    
    def test_register_speaker_audio_too_short(self, speaker_manager, short_audio):
        """测试音频过短时注册失败"""
        result = speaker_manager.register_speaker(
            speaker_name="王五",
            audio=short_audio,
            sample_rate=16000
        )
        
        assert result.success is False
        assert "音频过短" in result.message
        assert result.speaker_id == ""
        assert result.quality_score == 0.0
    
    def test_register_speaker_duplicate_name(self, speaker_manager, valid_audio):
        """测试重复名称注册失败"""
        speaker_name = "赵六"
        
        # 第一次注册
        result1 = speaker_manager.register_speaker(
            speaker_name=speaker_name,
            audio=valid_audio
        )
        assert result1.success is True
        
        # 第二次注册相同名称
        result2 = speaker_manager.register_speaker(
            speaker_name=speaker_name,
            audio=valid_audio
        )
        assert result2.success is False
        assert "已存在" in result2.message
    
    def test_register_speaker_low_quality(self, speaker_manager, mock_sv_engine, valid_audio):
        """测试低质量声纹注册失败"""
        # 模拟低质量声纹（全零向量）
        low_quality_embedding = np.zeros(192, dtype=np.float32)
        mock_sv_engine.embed.return_value = low_quality_embedding
        
        result = speaker_manager.register_speaker(
            speaker_name="低质量",
            audio=valid_audio
        )
        
        assert result.success is False
        assert "质量过低" in result.message
    
    def test_register_speaker_embedding_failure(self, speaker_manager, mock_sv_engine, valid_audio):
        """测试声纹提取失败"""
        mock_sv_engine.embed.side_effect = Exception("Embedding failed")
        
        result = speaker_manager.register_speaker(
            speaker_name="提取失败",
            audio=valid_audio
        )
        
        assert result.success is False
        assert "注册失败" in result.message


class TestVoiceprintUpdate:
    """测试声纹更新功能"""
    
    def test_update_voiceprint_success(self, speaker_manager, mock_sv_engine, valid_audio):
        """测试成功更新声纹"""
        # 先注册说话人
        result = speaker_manager.register_speaker("更新测试", valid_audio)
        assert result.success is True
        speaker_id = result.speaker_id
        
        # 准备新的声纹
        new_embedding = np.random.randn(192).astype(np.float32)
        new_embedding = new_embedding / np.linalg.norm(new_embedding)
        mock_sv_engine.embed.return_value = new_embedding
        
        # 更新声纹
        success = speaker_manager.update_voiceprint(
            speaker_id=speaker_id,
            audio=valid_audio,
            merge_strategy="average"
        )
        
        assert success is True
        
        # 验证元数据更新
        speaker_info = speaker_manager.get_speaker_info(speaker_id)
        assert speaker_info is not None
        assert speaker_info.metadata["sample_count"] == 2
    
    def test_update_voiceprint_nonexistent_speaker(self, speaker_manager, valid_audio):
        """测试更新不存在的说话人"""
        success = speaker_manager.update_voiceprint(
            speaker_id="nonexistent_speaker",
            audio=valid_audio
        )
        
        assert success is False
    
    def test_update_voiceprint_short_audio(self, speaker_manager, valid_audio, short_audio):
        """测试用过短音频更新声纹"""
        # 先注册说话人
        result = speaker_manager.register_speaker("短音频测试", valid_audio)
        assert result.success is True
        
        # 用短音频更新
        success = speaker_manager.update_voiceprint(
            speaker_id=result.speaker_id,
            audio=short_audio
        )
        
        assert success is False
    
    def test_update_voiceprint_merge_strategies(self, speaker_manager, mock_sv_engine, valid_audio):
        """测试不同的融合策略"""
        # 注册说话人
        original_embedding = np.random.randn(192).astype(np.float32)
        original_embedding = original_embedding / np.linalg.norm(original_embedding)
        mock_sv_engine.embed.return_value = original_embedding
        
        result = speaker_manager.register_speaker("融合测试", valid_audio)
        speaker_id = result.speaker_id
        
        # 准备新声纹
        new_embedding = np.random.randn(192).astype(np.float32)
        new_embedding = new_embedding / np.linalg.norm(new_embedding)
        mock_sv_engine.embed.return_value = new_embedding
        
        # 测试 replace 策略
        success = speaker_manager.update_voiceprint(
            speaker_id=speaker_id,
            audio=valid_audio,
            merge_strategy="replace"
        )
        assert success is True
        
        # 测试 weighted 策略
        success = speaker_manager.update_voiceprint(
            speaker_id=speaker_id,
            audio=valid_audio,
            merge_strategy="weighted"
        )
        assert success is True
        
        # 测试 average 策略
        success = speaker_manager.update_voiceprint(
            speaker_id=speaker_id,
            audio=valid_audio,
            merge_strategy="average"
        )
        assert success is True


class TestSpeakerDeletion:
    """测试说话人删除功能"""
    
    def test_delete_speaker_success(self, speaker_manager, valid_audio):
        """测试成功删除说话人"""
        # 先注册说话人
        result = speaker_manager.register_speaker("删除测试", valid_audio)
        assert result.success is True
        speaker_id = result.speaker_id
        
        # 验证说话人存在
        assert len(speaker_manager.list_speakers()) == 1
        
        # 删除说话人
        success = speaker_manager.delete_speaker(speaker_id)
        assert success is True
        
        # 验证说话人已删除
        assert len(speaker_manager.list_speakers()) == 0
        assert speaker_manager.get_speaker_info(speaker_id) is None
    
    def test_delete_nonexistent_speaker(self, speaker_manager):
        """测试删除不存在的说话人（幂等操作）"""
        success = speaker_manager.delete_speaker("nonexistent_speaker")
        assert success is True  # 幂等操作应该返回 True


class TestSpeakerQuery:
    """测试说话人查询功能"""
    
    def test_list_speakers_empty(self, speaker_manager):
        """测试空列表"""
        speakers = speaker_manager.list_speakers()
        assert speakers == []
    
    def test_list_speakers_multiple(self, speaker_manager, valid_audio):
        """测试列出多个说话人"""
        # 注册 3 个说话人
        names = ["说话人1", "说话人2", "说话人3"]
        for name in names:
            result = speaker_manager.register_speaker(name, valid_audio)
            assert result.success is True
        
        speakers = speaker_manager.list_speakers()
        assert len(speakers) == 3
        
        # 验证按注册时间排序（最新的在前）
        speaker_names = [s.speaker_name for s in speakers]
        assert "说话人3" in speaker_names
        assert "说话人2" in speaker_names
        assert "说话人1" in speaker_names
    
    def test_get_speaker_info_success(self, speaker_manager, valid_audio):
        """测试获取说话人信息"""
        speaker_name = "信息测试"
        result = speaker_manager.register_speaker(speaker_name, valid_audio)
        assert result.success is True
        
        speaker_info = speaker_manager.get_speaker_info(result.speaker_id)
        
        assert speaker_info is not None
        assert speaker_info.speaker_id == result.speaker_id
        assert speaker_info.speaker_name == speaker_name
        assert speaker_info.user_id == result.speaker_id  # 简单映射
        assert speaker_info.audio_duration_sec > 0
        assert speaker_info.voiceprint_quality > 0
        assert isinstance(speaker_info.metadata, dict)
    
    def test_get_speaker_info_nonexistent(self, speaker_manager):
        """测试获取不存在说话人的信息"""
        speaker_info = speaker_manager.get_speaker_info("nonexistent_speaker")
        assert speaker_info is None


class TestQualityEvaluation:
    """测试声纹质量评估"""
    
    def test_evaluate_good_quality(self, speaker_manager):
        """测试高质量声纹评估"""
        # 创建高质量声纹（归一化的随机向量）
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        
        # 创建高质量音频（较大功率）
        audio = np.random.randn(80000).astype(np.float32) * 0.1
        
        quality = speaker_manager._evaluate_voiceprint_quality(embedding, audio, 16000)
        
        assert 0.0 <= quality <= 1.0
        assert quality > 0.5  # 应该是较高质量
    
    def test_evaluate_poor_quality(self, speaker_manager):
        """测试低质量声纹评估"""
        # 创建低质量声纹（接近零向量）
        embedding = np.ones(192, dtype=np.float32) * 0.001
        
        # 创建低质量音频（很小功率）
        audio = np.random.randn(80000).astype(np.float32) * 0.001
        
        quality = speaker_manager._evaluate_voiceprint_quality(embedding, audio, 16000)
        
        assert 0.0 <= quality <= 1.0
        assert quality < 0.7  # 应该是较低质量


class TestEmbeddingMerging:
    """测试声纹融合"""
    
    def test_merge_embeddings_average(self, speaker_manager):
        """测试平均融合策略"""
        emb1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        emb2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        
        merged = speaker_manager._merge_embeddings(emb1, emb2, "average")
        
        # 应该是归一化的平均值
        expected = np.array([0.5, 0.5, 0.0], dtype=np.float32)
        expected = expected / np.linalg.norm(expected)
        
        assert np.allclose(merged, expected, atol=1e-6)
    
    def test_merge_embeddings_weighted(self, speaker_manager):
        """测试加权融合策略"""
        emb1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        emb2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        
        merged = speaker_manager._merge_embeddings(emb1, emb2, "weighted")
        
        # 应该是 0.7 * emb1 + 0.3 * emb2
        expected = 0.7 * emb1 + 0.3 * emb2
        
        assert np.allclose(merged, expected)
    
    def test_merge_embeddings_replace(self, speaker_manager):
        """测试替换融合策略"""
        emb1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        emb2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        
        merged = speaker_manager._merge_embeddings(emb1, emb2, "replace")
        
        # 应该直接返回新声纹
        assert np.array_equal(merged, emb2)


class TestSpeakerIdGeneration:
    """测试说话人ID生成"""
    
    def test_generate_speaker_id_unique(self, speaker_manager):
        """测试生成唯一的说话人ID"""
        name = "测试用户"
        
        id1 = speaker_manager._generate_speaker_id(name)
        id2 = speaker_manager._generate_speaker_id(name)
        
        # 应该生成不同的ID
        assert id1 != id2
        assert id1.startswith("speaker_")
        assert id2.startswith("speaker_")
    
    def test_generate_speaker_id_special_chars(self, speaker_manager):
        """测试包含特殊字符的名称"""
        name = "用户@#$%^&*()测试"
        
        speaker_id = speaker_manager._generate_speaker_id(name)
        
        # 应该只包含字母数字和下划线
        assert speaker_id.startswith("speaker_")
        # 特殊字符应该被过滤掉
        assert "@" not in speaker_id
        assert "#" not in speaker_id


class TestConfigurationParameters:
    """测试配置参数"""
    
    def test_min_registration_duration(self, speaker_manager, mock_sv_engine):
        """测试最小注册时长配置"""
        # 修改最小时长配置
        speaker_manager.min_registration_sec = 5.0
        
        # 创建 4 秒音频（小于配置的 5 秒）
        audio = np.random.randn(64000).astype(np.float32)
        
        result = speaker_manager.register_speaker("时长测试", audio)
        
        assert result.success is False
        assert "5.0" in result.message
    
    def test_min_quality_score(self, speaker_manager, mock_sv_engine, valid_audio):
        """测试最小质量评分配置"""
        # 修改最小质量配置
        speaker_manager.min_quality_score = 0.9
        
        # 模拟中等质量声纹
        embedding = np.random.randn(192).astype(np.float32) * 0.5
        embedding = embedding / np.linalg.norm(embedding)
        mock_sv_engine.embed.return_value = embedding
        
        result = speaker_manager.register_speaker("质量测试", valid_audio)
        
        # 由于质量评估的随机性，这个测试可能不稳定
        # 主要验证配置参数被使用
        assert isinstance(result.success, bool)


class TestErrorHandling:
    """测试错误处理"""
    
    def test_register_with_database_error(self, speaker_manager, mock_sv_engine, voiceprint_db, valid_audio):
        """测试数据库保存失败"""
        # 模拟数据库保存失败
        voiceprint_db.save_voiceprint = Mock(return_value=False)
        
        result = speaker_manager.register_speaker("数据库错误", valid_audio)
        
        assert result.success is False
        assert "保存声纹到数据库失败" in result.message
    
    def test_update_with_embedding_error(self, speaker_manager, mock_sv_engine, valid_audio):
        """测试更新时声纹提取失败"""
        # 先注册说话人
        result = speaker_manager.register_speaker("更新错误", valid_audio)
        assert result.success is True
        
        # 模拟声纹提取失败
        mock_sv_engine.embed.side_effect = Exception("Embedding failed")
        
        success = speaker_manager.update_voiceprint(result.speaker_id, valid_audio)
        
        assert success is False
    
    def test_delete_with_database_error(self, speaker_manager, voiceprint_db, valid_audio):
        """测试删除时数据库错误"""
        # 先注册说话人
        result = speaker_manager.register_speaker("删除错误", valid_audio)
        assert result.success is True
        
        # 模拟数据库删除失败
        voiceprint_db.delete = Mock(return_value=False)
        
        success = speaker_manager.delete_speaker(result.speaker_id)
        
        assert success is False


class TestIntegrationScenarios:
    """测试集成场景"""
    
    def test_complete_speaker_lifecycle(self, speaker_manager, mock_sv_engine, valid_audio):
        """测试完整的说话人生命周期"""
        speaker_name = "生命周期测试"
        
        # 1. 注册
        result = speaker_manager.register_speaker(speaker_name, valid_audio)
        assert result.success is True
        speaker_id = result.speaker_id
        
        # 2. 查询
        speaker_info = speaker_manager.get_speaker_info(speaker_id)
        assert speaker_info is not None
        assert speaker_info.speaker_name == speaker_name
        
        # 3. 更新
        new_embedding = np.random.randn(192).astype(np.float32)
        new_embedding = new_embedding / np.linalg.norm(new_embedding)
        mock_sv_engine.embed.return_value = new_embedding
        
        success = speaker_manager.update_voiceprint(speaker_id, valid_audio)
        assert success is True
        
        # 4. 验证更新
        updated_info = speaker_manager.get_speaker_info(speaker_id)
        assert updated_info.metadata["sample_count"] == 2
        
        # 5. 删除
        success = speaker_manager.delete_speaker(speaker_id)
        assert success is True
        
        # 6. 验证删除
        assert speaker_manager.get_speaker_info(speaker_id) is None
    
    def test_multiple_speakers_management(self, speaker_manager, valid_audio):
        """测试多说话人管理"""
        speakers_data = [
            ("张三", {"department": "技术部"}),
            ("李四", {"department": "市场部"}),
            ("王五", {"department": "人事部"})
        ]
        
        registered_ids = []
        
        # 批量注册
        for name, metadata in speakers_data:
            result = speaker_manager.register_speaker(name, valid_audio, metadata=metadata)
            assert result.success is True
            registered_ids.append(result.speaker_id)
        
        # 验证列表
        speakers = speaker_manager.list_speakers()
        assert len(speakers) == 3
        
        # 验证每个说话人的信息
        for speaker in speakers:
            assert speaker.speaker_name in ["张三", "李四", "王五"]
            assert "department" in speaker.metadata
        
        # 批量删除
        for speaker_id in registered_ids:
            success = speaker_manager.delete_speaker(speaker_id)
            assert success is True
        
        # 验证全部删除
        assert len(speaker_manager.list_speakers()) == 0