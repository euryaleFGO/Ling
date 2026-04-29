# -*- coding: utf-8 -*-
"""
VoiceprintDatabase 单元测试

测试覆盖：
- 保存和加载声纹向量
- 最佳匹配查找（包含阈值判断）
- 导入/导出功能
- 边界情况（空数据库、不存在的 speaker_id）
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.core.voiceprint_database import VoiceprintDatabase


@pytest.fixture
def temp_storage():
    """创建临时存储目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db(temp_storage):
    """创建 VoiceprintDatabase 实例"""
    return VoiceprintDatabase(temp_storage)


@pytest.fixture
def sample_embedding():
    """创建示例声纹向量（192维，已归一化）"""
    emb = np.random.randn(192).astype(np.float32)
    # 归一化
    emb = emb / np.linalg.norm(emb)
    return emb


class TestVoiceprintDatabase:
    """VoiceprintDatabase 测试套件"""

    def test_init_creates_storage_directory(self, temp_storage):
        """测试初始化时创建存储目录"""
        storage_path = temp_storage / "voiceprints"
        db = VoiceprintDatabase(storage_path)
        
        assert storage_path.exists()
        assert storage_path.is_dir()

    def test_save_and_load_voiceprint(self, db, sample_embedding):
        """测试保存和加载声纹向量"""
        speaker_id = "test_speaker_001"
        
        # 保存
        result = db.save_voiceprint(speaker_id, sample_embedding)
        assert result is True
        
        # 加载
        loaded = db.load_voiceprint(speaker_id)
        assert loaded is not None
        assert np.allclose(loaded, sample_embedding)

    def test_save_with_metadata(self, db, sample_embedding):
        """测试保存声纹时包含元数据"""
        speaker_id = "test_speaker_002"
        metadata = {
            "speaker_name": "张三",
            "registered_at": "2025-03-16T10:30:00",
            "audio_duration_sec": 5.2
        }
        
        # 保存
        result = db.save_voiceprint(speaker_id, sample_embedding, metadata)
        assert result is True
        
        # 加载元数据
        loaded_metadata = db.load_metadata(speaker_id)
        assert loaded_metadata is not None
        assert loaded_metadata["speaker_name"] == "张三"
        assert loaded_metadata["audio_duration_sec"] == 5.2
        assert "last_updated_at" in loaded_metadata

    def test_load_nonexistent_voiceprint(self, db):
        """测试加载不存在的声纹"""
        result = db.load_voiceprint("nonexistent_speaker")
        assert result is None

    def test_find_best_match_with_exact_match(self, db, sample_embedding):
        """测试查找最佳匹配（完全匹配）"""
        speaker_id = "test_speaker_003"
        
        # 保存声纹
        db.save_voiceprint(speaker_id, sample_embedding)
        
        # 查找匹配（使用相同的向量）
        matched_id, score = db.find_best_match(sample_embedding, threshold=0.75)
        
        assert matched_id == speaker_id
        assert score >= 0.99  # 应该接近 1.0

    def test_find_best_match_with_similar_embedding(self, db, sample_embedding):
        """测试查找最佳匹配（相似向量）"""
        speaker_id = "test_speaker_004"
        
        # 保存声纹
        db.save_voiceprint(speaker_id, sample_embedding)
        
        # 创建相似的向量（添加小噪声）
        similar_emb = sample_embedding + np.random.randn(192).astype(np.float32) * 0.05
        similar_emb = similar_emb / np.linalg.norm(similar_emb)
        
        # 查找匹配
        matched_id, score = db.find_best_match(similar_emb, threshold=0.70)
        
        # 应该能匹配到（相似度应该较高）
        assert matched_id == speaker_id
        assert score >= 0.70

    def test_find_best_match_below_threshold(self, db, sample_embedding):
        """测试查找最佳匹配（低于阈值）"""
        speaker_id = "test_speaker_005"
        
        # 保存声纹
        db.save_voiceprint(speaker_id, sample_embedding)
        
        # 创建完全不同的向量
        different_emb = np.random.randn(192).astype(np.float32)
        different_emb = different_emb / np.linalg.norm(different_emb)
        
        # 查找匹配（使用高阈值）
        matched_id, score = db.find_best_match(different_emb, threshold=0.95)
        
        # 应该找不到匹配
        assert matched_id is None
        assert score < 0.95

    def test_find_best_match_empty_database(self, db, sample_embedding):
        """测试在空数据库中查找匹配"""
        matched_id, score = db.find_best_match(sample_embedding, threshold=0.75)
        
        assert matched_id is None
        assert score == 0.0

    def test_find_best_match_multiple_speakers(self, db):
        """测试在多个说话人中查找最佳匹配"""
        # 创建 3 个不同的声纹
        emb1 = np.random.randn(192).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        
        emb2 = np.random.randn(192).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)
        
        emb3 = np.random.randn(192).astype(np.float32)
        emb3 = emb3 / np.linalg.norm(emb3)
        
        # 保存
        db.save_voiceprint("speaker_1", emb1)
        db.save_voiceprint("speaker_2", emb2)
        db.save_voiceprint("speaker_3", emb3)
        
        # 查找与 emb2 最相似的
        matched_id, score = db.find_best_match(emb2, threshold=0.75)
        
        assert matched_id == "speaker_2"
        assert score >= 0.99

    def test_list_all_empty(self, db):
        """测试列出所有说话人（空数据库）"""
        result = db.list_all()
        assert result == []

    def test_list_all_with_speakers(self, db, sample_embedding):
        """测试列出所有说话人"""
        # 添加多个说话人
        db.save_voiceprint("speaker_1", sample_embedding)
        db.save_voiceprint("speaker_2", sample_embedding)
        db.save_voiceprint("speaker_3", sample_embedding)
        
        result = db.list_all()
        
        assert len(result) == 3
        assert "speaker_1" in result
        assert "speaker_2" in result
        assert "speaker_3" in result

    def test_delete_voiceprint(self, db, sample_embedding):
        """测试删除声纹"""
        speaker_id = "test_speaker_006"
        
        # 保存
        db.save_voiceprint(speaker_id, sample_embedding)
        assert db.load_voiceprint(speaker_id) is not None
        
        # 删除
        result = db.delete(speaker_id)
        assert result is True
        
        # 验证已删除
        assert db.load_voiceprint(speaker_id) is None
        assert speaker_id not in db.list_all()

    def test_delete_nonexistent_voiceprint(self, db):
        """测试删除不存在的声纹"""
        result = db.delete("nonexistent_speaker")
        # 应该返回 True（幂等操作）
        assert result is True

    def test_export_voiceprint(self, db, sample_embedding, temp_storage):
        """测试导出声纹"""
        speaker_id = "test_speaker_007"
        
        # 保存声纹
        db.save_voiceprint(speaker_id, sample_embedding, metadata={"name": "测试"})
        
        # 导出
        export_path = temp_storage / "exported.npy"
        result = db.export_voiceprint(speaker_id, export_path)
        
        assert result is True
        assert export_path.exists()
        
        # 验证导出的数据
        exported_emb = np.load(export_path)
        assert np.allclose(exported_emb, sample_embedding)
        
        # 验证元数据也被导出
        export_json = export_path.with_suffix('.json')
        assert export_json.exists()

    def test_export_nonexistent_voiceprint(self, db, temp_storage):
        """测试导出不存在的声纹"""
        export_path = temp_storage / "exported.npy"
        result = db.export_voiceprint("nonexistent_speaker", export_path)
        
        assert result is False
        assert not export_path.exists()

    def test_import_voiceprint(self, db, sample_embedding, temp_storage):
        """测试导入声纹"""
        # 创建导入文件
        import_path = temp_storage / "import.npy"
        np.save(import_path, sample_embedding)
        
        # 导入
        speaker_id = "imported_speaker"
        result = db.import_voiceprint(import_path, speaker_id)
        
        assert result is True
        
        # 验证导入的数据
        loaded = db.load_voiceprint(speaker_id)
        assert loaded is not None
        assert np.allclose(loaded, sample_embedding)

    def test_import_voiceprint_with_metadata(self, db, sample_embedding, temp_storage):
        """测试导入声纹（包含元数据）"""
        # 创建导入文件
        import_path = temp_storage / "import.npy"
        np.save(import_path, sample_embedding)
        
        # 创建元数据文件
        import_json = import_path.with_suffix('.json')
        import json
        with open(import_json, 'w', encoding='utf-8') as f:
            json.dump({"name": "导入的说话人"}, f)
        
        # 导入
        speaker_id = "imported_speaker_with_meta"
        result = db.import_voiceprint(import_path, speaker_id)
        
        assert result is True
        
        # 验证元数据
        metadata = db.load_metadata(speaker_id)
        assert metadata is not None
        assert metadata["name"] == "导入的说话人"

    def test_memory_index_persistence(self, db, sample_embedding):
        """测试内存索引在保存后立即可用"""
        speaker_id = "test_speaker_008"
        
        # 保存
        db.save_voiceprint(speaker_id, sample_embedding)
        
        # 立即查找（应该从内存索引读取）
        matched_id, score = db.find_best_match(sample_embedding, threshold=0.75)
        
        assert matched_id == speaker_id
        assert score >= 0.99

    def test_memory_index_loaded_on_init(self, temp_storage, sample_embedding):
        """测试初始化时加载所有声纹到内存"""
        # 创建第一个数据库实例并保存数据
        db1 = VoiceprintDatabase(temp_storage)
        db1.save_voiceprint("speaker_1", sample_embedding)
        db1.save_voiceprint("speaker_2", sample_embedding)
        
        # 创建第二个数据库实例（应该自动加载）
        db2 = VoiceprintDatabase(temp_storage)
        
        # 验证数据已加载到内存
        assert len(db2.list_all()) == 2
        assert "speaker_1" in db2.list_all()
        assert "speaker_2" in db2.list_all()
        
        # 验证可以查找
        matched_id, score = db2.find_best_match(sample_embedding, threshold=0.75)
        assert matched_id in ["speaker_1", "speaker_2"]
