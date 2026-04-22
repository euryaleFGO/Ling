# -*- coding: utf-8 -*-
"""
声纹数据库模块

功能：
- 声纹向量的保存、加载、删除
- 基于余弦相似度的最佳匹配查找
- 内存索引优化（将所有声纹加载到内存）
- 声纹导入/导出功能

存储格式：
- 声纹向量：{storage_path}/{speaker_id}.npy
- 元数据：{storage_path}/{speaker_id}.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


class VoiceprintDatabase:
    """声纹数据库"""

    def __init__(self, storage_path: Path):
        """
        初始化数据库

        Args:
            storage_path: 存储目录（存储 .npy 文件）
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 内存索引：{speaker_id: embedding}
        self._memory_index: Dict[str, np.ndarray] = {}
        
        # 加载所有声纹到内存
        self._load_all_to_memory()

    def _load_all_to_memory(self) -> None:
        """将所有声纹加载到内存"""
        for npy_file in self.storage_path.glob("*.npy"):
            speaker_id = npy_file.stem
            try:
                embedding = np.load(npy_file)
                self._memory_index[speaker_id] = embedding
            except Exception:
                # 忽略损坏的文件
                pass

    def save_voiceprint(
        self,
        speaker_id: str,
        embedding: np.ndarray,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        保存声纹向量

        Args:
            speaker_id: 说话人 ID
            embedding: 声纹向量
            metadata: 元数据（可选）

        Returns:
            是否成功
        """
        try:
            # 保存声纹向量
            npy_path = self.storage_path / f"{speaker_id}.npy"
            np.save(npy_path, embedding)
            
            # 保存元数据
            if metadata is not None:
                json_path = self.storage_path / f"{speaker_id}.json"
                # 添加时间戳
                metadata_with_time = {
                    **metadata,
                    "last_updated_at": datetime.now().isoformat()
                }
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata_with_time, f, ensure_ascii=False, indent=2)
            
            # 更新内存索引
            self._memory_index[speaker_id] = embedding
            
            return True
        except Exception:
            return False

    def load_voiceprint(self, speaker_id: str) -> Optional[np.ndarray]:
        """
        加载声纹向量

        Args:
            speaker_id: 说话人 ID

        Returns:
            声纹向量，如果不存在则返回 None
        """
        # 优先从内存索引读取
        if speaker_id in self._memory_index:
            return self._memory_index[speaker_id]
        
        # 如果内存中没有，尝试从文件加载
        npy_path = self.storage_path / f"{speaker_id}.npy"
        if not npy_path.exists():
            return None
        
        try:
            embedding = np.load(npy_path)
            # 加载后更新内存索引
            self._memory_index[speaker_id] = embedding
            return embedding
        except Exception:
            return None

    def find_best_match(
        self,
        query_embedding: np.ndarray,
        threshold: float = 0.75
    ) -> Tuple[Optional[str], float]:
        """
        查找最佳匹配的说话人

        Args:
            query_embedding: 查询声纹向量
            threshold: 相似度阈值

        Returns:
            (speaker_id, score) 或 (None, 0.0)
        """
        if not self._memory_index:
            return None, 0.0
        
        # 批量计算相似度（向量化）
        speaker_ids = list(self._memory_index.keys())
        embeddings = np.stack([self._memory_index[sid] for sid in speaker_ids])
        
        # 余弦相似度（假设已归一化，使用点积）
        scores = embeddings @ query_embedding
        
        # 找到最大值
        best_idx = np.argmax(scores)
        best_score = float(scores[best_idx])
        
        if best_score >= threshold:
            return speaker_ids[best_idx], best_score
        else:
            return None, best_score

    def list_all(self) -> List[str]:
        """
        列出所有 speaker_id

        Returns:
            speaker_id 列表
        """
        return list(self._memory_index.keys())

    def delete(self, speaker_id: str) -> bool:
        """
        删除声纹

        Args:
            speaker_id: 说话人 ID

        Returns:
            是否成功
        """
        try:
            # 删除声纹文件
            npy_path = self.storage_path / f"{speaker_id}.npy"
            if npy_path.exists():
                npy_path.unlink()
            
            # 删除元数据文件
            json_path = self.storage_path / f"{speaker_id}.json"
            if json_path.exists():
                json_path.unlink()
            
            # 从内存索引中删除
            if speaker_id in self._memory_index:
                del self._memory_index[speaker_id]
            
            return True
        except Exception:
            return False

    def export_voiceprint(self, speaker_id: str, output_path: Path) -> bool:
        """
        导出声纹到文件

        Args:
            speaker_id: 说话人 ID
            output_path: 输出文件路径

        Returns:
            是否成功
        """
        try:
            embedding = self.load_voiceprint(speaker_id)
            if embedding is None:
                return False
            
            # 保存到指定路径
            np.save(output_path, embedding)
            
            # 如果有元数据，也导出
            json_path = self.storage_path / f"{speaker_id}.json"
            if json_path.exists():
                output_json = output_path.with_suffix('.json')
                with open(json_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                with open(output_json, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception:
            return False

    def import_voiceprint(self, input_path: Path, speaker_id: str) -> bool:
        """
        从文件导入声纹

        Args:
            input_path: 输入文件路径
            speaker_id: 说话人 ID

        Returns:
            是否成功
        """
        try:
            # 加载声纹向量
            embedding = np.load(input_path)
            
            # 尝试加载元数据
            metadata = None
            input_json = input_path.with_suffix('.json')
            if input_json.exists():
                with open(input_json, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            
            # 保存到数据库
            return self.save_voiceprint(speaker_id, embedding, metadata)
        except Exception:
            return False

    def load_metadata(self, speaker_id: str) -> Optional[Dict]:
        """
        加载说话人元数据

        Args:
            speaker_id: 说话人 ID

        Returns:
            元数据字典，如果不存在则返回 None
        """
        json_path = self.storage_path / f"{speaker_id}.json"
        if not json_path.exists():
            return None
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
