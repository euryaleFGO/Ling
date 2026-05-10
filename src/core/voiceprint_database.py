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
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

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

        # unknown 计数器
        self._counter_file = self.storage_path / "_counter.json"
        self._next_unknown_id: int = self._load_counter()
        self._id_lock = threading.Lock()

        # 加载所有声纹到内存
        self._load_all_to_memory()

    def _load_all_to_memory(self) -> None:
        """将所有声纹加载到内存"""
        for npy_file in self.storage_path.glob("*.npy"):
            speaker_id = npy_file.stem
            try:
                embedding = np.load(npy_file)
                self._memory_index[speaker_id] = embedding
            except Exception as e:
                logger.debug(f"Failed to load voiceprint file {npy_file.name}, skipping corrupted file: {e}")

    def _load_counter(self) -> int:
        """从 _counter.json 加载 unknown 计数器"""
        if not self._counter_file.exists():
            return 1
        try:
            with open(self._counter_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return int(data.get("next_unknown_id", 1))
        except Exception as e:
            logger.debug(f"Failed to load counter file: {e}")
            return 1

    def _save_counter(self) -> None:
        """持久化 unknown 计数器"""
        try:
            with open(self._counter_file, 'w', encoding='utf-8') as f:
                json.dump({"next_unknown_id": self._next_unknown_id}, f)
        except Exception as e:
            logger.warning(f"Failed to save counter file: {e}")

    def get_next_unknown_id(self) -> str:
        """
        获取下一个 unknown 说话人 ID 并自增（线程安全）

        Returns:
            unknown_XX 格式的 ID
        """
        with self._id_lock:
            speaker_id = f"unknown_{self._next_unknown_id:02d}"
            self._next_unknown_id += 1
            self._save_counter()
            return speaker_id

    def rename_speaker(self, old_id: str, new_id: str) -> bool:
        """
        重命名说话人（重命名 .npy 和 .json 文件，更新内存索引）

        Args:
            old_id: 原 speaker_id
            new_id: 新 speaker_id

        Returns:
            是否成功
        """
        try:
            old_npy = self.storage_path / f"{old_id}.npy"
            old_json = self.storage_path / f"{old_id}.json"
            new_npy = self.storage_path / f"{new_id}.npy"
            new_json = self.storage_path / f"{new_id}.json"

            if not old_npy.exists():
                logger.warning(f"Cannot rename: voiceprint '{old_id}' not found")
                return False

            # 检查目标是否已存在
            if new_npy.exists():
                logger.warning(f"Cannot rename: target '{new_id}' already exists")
                return False

            # 重命名文件
            old_npy.rename(new_npy)
            if old_json.exists():
                old_json.rename(new_json)

            # 更新内存索引
            if old_id in self._memory_index:
                self._memory_index[new_id] = self._memory_index.pop(old_id)

            # 更新 metadata 中的 speaker_name
            metadata = self.load_metadata(new_id)
            if metadata:
                metadata["speaker_name"] = new_id
                metadata["user_id"] = new_id
                json_path = self.storage_path / f"{new_id}.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"Renamed speaker: {old_id} -> {new_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to rename speaker '{old_id}' to '{new_id}': {e}")
            return False

    def save_voiceprint(
        self,
        speaker_id: str,
        embedding: np.ndarray,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        保存声纹向量（支持同一说话人多条声纹）

        同一 speaker_id 多次调用会追加而非覆盖。
        存储格式: (N, D) 2D 数组，N=声纹条数，D=特征维度。

        Args:
            speaker_id: 说话人 ID
            embedding: 声纹向量 (D,) 或 (1, D)
            metadata: 元数据（可选）

        Returns:
            是否成功
        """
        try:
            emb = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
            npy_path = self.storage_path / f"{speaker_id}.npy"

            # 追加已有 embedding
            if npy_path.exists():
                try:
                    existing = np.load(npy_path)
                    if existing.ndim == 1:
                        existing = existing.reshape(1, -1)
                    emb = np.concatenate([existing, emb], axis=0)
                except Exception:
                    pass  # 文件损坏，用新 embedding 覆盖

            np.save(npy_path, emb)

            # 保存元数据
            if metadata is not None:
                json_path = self.storage_path / f"{speaker_id}.json"
                metadata_with_time = {
                    **metadata,
                    "last_updated_at": datetime.now().isoformat()
                }
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata_with_time, f, ensure_ascii=False, indent=2)

            # 更新内存索引（存完整 2D 数组）
            self._memory_index[speaker_id] = emb

            return True
        except Exception as e:
            logger.warning(f"Failed to save voiceprint for speaker '{speaker_id}': {e}")
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
        except Exception as e:
            logger.debug(f"Failed to load voiceprint from file for speaker '{speaker_id}': {e}")
            return None

    def find_best_match(
        self,
        query_embedding: np.ndarray,
        threshold: float = 0.75
    ) -> Tuple[Optional[str], float]:
        """
        查找最佳匹配的说话人

        支持每个说话人多条声纹（2D 数组），取最高匹配分。

        Args:
            query_embedding: 查询声纹向量 (D,)
            threshold: 相似度阈值

        Returns:
            (speaker_id, score) 或 (None, best_score)
        """
        if not self._memory_index:
            return None, 0.0

        q = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        best_score = -1.0
        best_sid = None

        for sid, emb in self._memory_index.items():
            emb_arr = np.asarray(emb, dtype=np.float32)
            if emb_arr.ndim == 1:
                # 单条声纹
                score = float(np.dot(emb_arr, q))
            else:
                # 多条声纹 (N, D)，取最高分
                scores = emb_arr @ q
                score = float(np.max(scores))
            if score > best_score:
                best_score = score
                best_sid = sid

        if best_score >= threshold:
            return best_sid, best_score
        else:
            return None, best_score

    def list_all(self) -> List[str]:
        """
        列出所有 speaker_id

        Returns:
            speaker_id 列表
        """
        return list(self._memory_index.keys())

    def get_stats(self) -> dict:
        """Return database statistics."""
        total_embeddings = 0
        for v in self._memory_index.values():
            total_embeddings += 1 if v.ndim == 1 else v.shape[0]

        storage_bytes = 0
        for f in self.storage_path.glob("*.npy"):
            try:
                storage_bytes += f.stat().st_size
            except OSError:
                pass

        unknown_count = sum(
            1 for sid in self._memory_index
            if sid.startswith("unknown_")
        )

        return {
            "total_speakers": len(self._memory_index),
            "total_embeddings": total_embeddings,
            "unknown_speakers": unknown_count,
            "named_speakers": len(self._memory_index) - unknown_count,
            "storage_bytes": storage_bytes,
        }

    def cleanup_unknowns(self, max_age_days: int = 7) -> int:
        """Remove unknown_XX entries older than max_age_days.

        Returns:
            Number of entries removed.
        """
        import time
        removed = 0
        cutoff = time.time() - max_age_days * 86400

        for sid in list(self._memory_index.keys()):
            if not sid.startswith("unknown_"):
                continue
            json_path = self.storage_path / f"{sid}.json"
            if json_path.exists():
                try:
                    mtime = json_path.stat().st_mtime
                    if mtime < cutoff:
                        self.delete(sid)
                        removed += 1
                except OSError:
                    pass
            else:
                npy_path = self.storage_path / f"{sid}.npy"
                if npy_path.exists():
                    try:
                        if npy_path.stat().st_mtime < cutoff:
                            self.delete(sid)
                            removed += 1
                    except OSError:
                        pass

        if removed:
            logger.info(f"[voiceprint] cleaned up {removed} stale unknown entries")
        return removed

    def get_embedding_count(self, speaker_id: str) -> int:
        """Return number of embeddings stored for a speaker."""
        emb = self._memory_index.get(speaker_id)
        if emb is None:
            return 0
        return 1 if emb.ndim == 1 else emb.shape[0]

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
        except Exception as e:
            logger.warning(f"Failed to delete voiceprint for speaker '{speaker_id}': {e}")
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
        except Exception as e:
            logger.warning(f"Failed to export voiceprint for speaker '{speaker_id}' to {output_path}: {e}")
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
        except Exception as e:
            logger.warning(f"Failed to import voiceprint from {input_path} for speaker '{speaker_id}': {e}")
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
        except Exception as e:
            logger.debug(f"Failed to load metadata for speaker '{speaker_id}': {e}")
            return None
