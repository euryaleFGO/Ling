# -*- coding: utf-8 -*-
"""
说话人管理器模块

功能：
- 说话人注册、更新、删除管理
- 声纹质量评估
- 音频时长验证
- 声纹融合策略
- 说话人信息查询

使用场景：
- GUI 说话人管理界面的后端支持
- 批量说话人操作
- 声纹数据维护
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from core.log import log
from core.sv_engine import SVEngine
from core.voiceprint_database import VoiceprintDatabase


@dataclass
class RegisterResult:
    """说话人注册结果"""
    speaker_id: str
    success: bool
    message: str
    quality_score: float = 0.0


@dataclass
class SpeakerInfo:
    """说话人信息"""
    speaker_id: str
    speaker_name: str
    user_id: str                 # 关联的 user_id
    registered_at: datetime
    last_active_at: datetime
    audio_duration_sec: float    # 注册音频时长
    voiceprint_quality: float    # 声纹质量评分 (0.0-1.0)
    metadata: Dict               # 额外信息


class SpeakerManager:
    """
    说话人管理器
    
    功能：
    - 注册新说话人
    - 更新说话人声纹
    - 删除说话人
    - 查询说话人信息
    - 声纹质量评估
    """
    
    def __init__(
        self,
        sv_engine: SVEngine,
        voiceprint_db: VoiceprintDatabase,
        user_profile_db = None  # UserProfileDatabase，暂时可选
    ):
        """
        初始化管理器
        
        Args:
            sv_engine: 声纹提取引擎
            voiceprint_db: 声纹数据库
            user_profile_db: 用户档案数据库（可选）
        """
        self.sv_engine = sv_engine
        self.voiceprint_db = voiceprint_db
        self.user_profile_db = user_profile_db
        
        # 配置参数
        self.min_registration_sec = 3.0  # 最小注册音频时长
        self.min_quality_score = 0.5     # 最小质量评分
    
    def register_speaker(
        self,
        speaker_name: str,
        audio: np.ndarray,
        sample_rate: int = 16000,
        metadata: Optional[Dict] = None
    ) -> RegisterResult:
        """
        注册新说话人
        
        Args:
            speaker_name: 说话人名称
            audio: 音频样本（建议 >3 秒）
            sample_rate: 采样率
            metadata: 额外元数据（昵称、偏好等）
            
        Returns:
            RegisterResult: 包含 speaker_id, success, message
        """
        try:
            # 1. 验证音频时长
            duration_sec = len(audio) / sample_rate
            if duration_sec < self.min_registration_sec:
                return RegisterResult(
                    speaker_id="",
                    success=False,
                    message=f"音频过短，请提供至少 {self.min_registration_sec} 秒的清晰语音",
                    quality_score=0.0
                )
            
            # 2. 检查说话人名称是否已存在
            existing_speakers = self.list_speakers()
            for speaker in existing_speakers:
                if speaker.speaker_name == speaker_name:
                    return RegisterResult(
                        speaker_id="",
                        success=False,
                        message=f"说话人名称 '{speaker_name}' 已存在，请使用不同的名称",
                        quality_score=0.0
                    )
            
            # 3. 提取声纹特征
            embedding = self.sv_engine.embed(audio, sample_rate=sample_rate)
            
            # 4. 评估声纹质量
            quality_score = self._evaluate_voiceprint_quality(embedding, audio, sample_rate)
            if quality_score < self.min_quality_score:
                return RegisterResult(
                    speaker_id="",
                    success=False,
                    message=f"声纹质量过低 ({quality_score:.2f} < {self.min_quality_score})，请重新录制清晰的语音",
                    quality_score=quality_score
                )
            
            # 5. 生成唯一的 speaker_id
            speaker_id = self._generate_speaker_id(speaker_name)
            
            # 6. 准备元数据
            now = datetime.now()
            full_metadata = {
                "speaker_id": speaker_id,
                "speaker_name": speaker_name,
                "user_id": speaker_id,  # 简单映射：speaker_id 作为 user_id
                "registered_at": now.isoformat(),
                "last_active_at": now.isoformat(),
                "audio_duration_sec": duration_sec,
                "embedding_dim": len(embedding),
                "model_id": getattr(self.sv_engine, 'model_id', 'unknown'),
                "quality_score": quality_score,
                "sample_count": 1,
                **(metadata or {})
            }
            
            # 7. 保存声纹到数据库
            success = self.voiceprint_db.save_voiceprint(
                speaker_id=speaker_id,
                embedding=embedding,
                metadata=full_metadata
            )
            
            if not success:
                return RegisterResult(
                    speaker_id="",
                    success=False,
                    message="保存声纹到数据库失败",
                    quality_score=quality_score
                )
            
            # 8. 更新用户档案数据库（如果可用）
            if self.user_profile_db:
                try:
                    self._update_user_profile(speaker_id, speaker_name, full_metadata)
                except Exception as e:
                    log.warn(f"更新用户档案失败: {e}")
            
            log.info(f"[说话人管理] 注册成功: {speaker_name} ({speaker_id}), 质量={quality_score:.2f}")
            
            return RegisterResult(
                speaker_id=speaker_id,
                success=True,
                message=f"说话人 '{speaker_name}' 注册成功",
                quality_score=quality_score
            )
            
        except Exception as e:
            log.error(f"[说话人管理] 注册失败: {type(e).__name__}: {e}")
            return RegisterResult(
                speaker_id="",
                success=False,
                message=f"注册失败: {str(e)}",
                quality_score=0.0
            )

    def register_unknown(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> RegisterResult:
        """
        自动注册未知说话人（unknown_XX）

        跳过最低质量检查，只要能提取声纹就行。

        Args:
            audio: 音频样本
            sample_rate: 采样率

        Returns:
            RegisterResult: 包含 speaker_id (unknown_XX), success, message
        """
        try:
            # 1. 获取下一个 unknown ID
            speaker_id = self.voiceprint_db.get_next_unknown_id()

            # 2. 提取声纹特征
            embedding = self.sv_engine.embed(audio, sample_rate=sample_rate)

            # 3. 简单质量检查（仅检查向量是否有效，不检查最低质量）
            quality_score = self._evaluate_voiceprint_quality(embedding, audio, sample_rate)
            norm = float(np.linalg.norm(embedding))
            if norm < 0.01:
                return RegisterResult(
                    speaker_id="",
                    success=False,
                    message="声纹提取失败（向量无效）",
                    quality_score=0.0
                )

            # 4. 准备元数据
            duration_sec = len(audio) / sample_rate
            now = datetime.now()
            full_metadata = {
                "speaker_id": speaker_id,
                "speaker_name": speaker_id,
                "user_id": speaker_id,
                "registered_at": now.isoformat(),
                "last_active_at": now.isoformat(),
                "audio_duration_sec": duration_sec,
                "embedding_dim": len(embedding),
                "model_id": getattr(self.sv_engine, 'model_id', 'unknown'),
                "quality_score": quality_score,
                "sample_count": 1,
                "is_unknown": True,
            }

            # 5. 保存声纹到数据库
            success = self.voiceprint_db.save_voiceprint(
                speaker_id=speaker_id,
                embedding=embedding,
                metadata=full_metadata
            )

            if not success:
                return RegisterResult(
                    speaker_id="",
                    success=False,
                    message="保存声纹到数据库失败",
                    quality_score=quality_score
                )

            log.info(f"[说话人管理] 自动注册 unknown: {speaker_id}, 质量={quality_score:.2f}")

            return RegisterResult(
                speaker_id=speaker_id,
                success=True,
                message=f"未知说话人自动注册为 '{speaker_id}'",
                quality_score=quality_score
            )

        except Exception as e:
            log.error(f"[说话人管理] unknown 注册失败: {type(e).__name__}: {e}")
            return RegisterResult(
                speaker_id="",
                success=False,
                message=f"注册失败: {str(e)}",
                quality_score=0.0
            )

    def rename_speaker(self, old_speaker_id: str, new_name: str) -> bool:
        """
        重命名说话人

        Args:
            old_speaker_id: 原 speaker_id（如 unknown_01）
            new_name: 新名称（如 张三）

        Returns:
            是否成功
        """
        try:
            # 1. 检查原说话人是否存在
            existing = self.voiceprint_db.load_voiceprint(old_speaker_id)
            if existing is None:
                log.warn(f"[说话人管理] 重命名失败: 说话人 '{old_speaker_id}' 不存在")
                return False

            # 2. 生成新 ID
            new_speaker_id = self._generate_speaker_id(new_name)

            # 3. 检查新名称是否已存在
            existing_speakers = self.list_speakers()
            for speaker in existing_speakers:
                if speaker.speaker_name == new_name:
                    log.warn(f"[说话人管理] 重命名失败: 名称 '{new_name}' 已存在")
                    return False

            # 4. 调用数据库重命名
            success = self.voiceprint_db.rename_speaker(old_speaker_id, new_speaker_id)
            if not success:
                return False

            # 5. 更新 metadata
            metadata = self.voiceprint_db.load_metadata(new_speaker_id) or {}
            metadata["speaker_name"] = new_name
            metadata["user_id"] = new_speaker_id
            metadata["is_unknown"] = False
            metadata["renamed_from"] = old_speaker_id
            metadata["renamed_at"] = datetime.now().isoformat()

            # 重新保存 metadata
            embedding = self.voiceprint_db.load_voiceprint(new_speaker_id)
            if embedding is not None:
                self.voiceprint_db.save_voiceprint(
                    speaker_id=new_speaker_id,
                    embedding=embedding,
                    metadata=metadata
                )

            # 6. 更新用户档案（如果可用）
            if self.user_profile_db:
                try:
                    self._update_user_profile(new_speaker_id, new_name, metadata)
                except Exception as e:
                    log.warn(f"更新用户档案失败: {e}")

            log.info(f"[说话人管理] 重命名成功: {old_speaker_id} -> {new_name} ({new_speaker_id})")
            return True

        except Exception as e:
            log.error(f"[说话人管理] 重命名失败: {type(e).__name__}: {e}")
            return False

    def identify(self, embedding: np.ndarray) -> tuple[str, float]:
        """Match an embedding against the voiceprint database.

        Returns (speaker_id, score). Returns ("unknown", 0.0) if no match.
        """
        if not self.voiceprint_db:
            return "unknown", 0.0
        try:
            result = self.voiceprint_db.find_best_match(embedding)
            if result:
                speaker_id, score = result
                if speaker_id is not None:
                    return speaker_id, score
            return "unknown", 0.0
        except Exception as e:
            log.warning(f"[SpeakerManager] identify failed: {e}")
            return "unknown", 0.0

    def register_embedding(self, name: str, embedding: np.ndarray) -> bool:
        """Register a speaker with a pre-computed embedding.

        Used by passive registration flow where embedding was captured
        during the first utterance, before the speaker identified themselves.
        """
        if not self.voiceprint_db:
            return False
        try:
            # Check if name already exists by iterating all speakers
            existing_speaker_id: Optional[str] = None
            for sid in self.voiceprint_db.list_all():
                metadata = self.voiceprint_db.load_metadata(sid)
                if metadata and metadata.get("speaker_name") == name:
                    existing_speaker_id = sid
                    break

            if existing_speaker_id is not None:
                # Update existing speaker's embedding (merge)
                old_emb = self.voiceprint_db.load_voiceprint(existing_speaker_id)
                if old_emb is not None:
                    merged = (old_emb + embedding) / 2
                    merged = merged / np.linalg.norm(merged)
                    metadata = self.voiceprint_db.load_metadata(existing_speaker_id) or {}
                    metadata["last_active_at"] = datetime.now().isoformat()
                    metadata["sample_count"] = metadata.get("sample_count", 1) + 1
                    self.voiceprint_db.save_voiceprint(existing_speaker_id, merged, metadata)
                    log.info(f"[SpeakerManager] merged embedding for '{name}' ({existing_speaker_id})")
                    return True

            # Generate speaker ID from name
            speaker_id = name.replace(" ", "_").lower()
            now = datetime.now()
            metadata = {
                "speaker_id": speaker_id,
                "speaker_name": name,
                "user_id": speaker_id,
                "registered_at": now.isoformat(),
                "last_active_at": now.isoformat(),
                "sample_count": 1,
                "embedding_dim": len(embedding),
                "model_id": getattr(self.sv_engine, 'model_id', 'unknown'),
            }
            self.voiceprint_db.save_voiceprint(speaker_id, embedding, metadata)
            log.info(f"[SpeakerManager] registered new speaker: '{name}' (id={speaker_id})")
            return True
        except Exception as e:
            log.error(f"[SpeakerManager] register_embedding failed: {e}")
            return False

    def update_voiceprint(
        self,
        speaker_id: str,
        audio: np.ndarray,
        sample_rate: int = 16000,
        merge_strategy: str = "average"
    ) -> bool:
        """
        更新说话人声纹（添加新样本）
        
        Args:
            speaker_id: 说话人 ID
            audio: 新音频样本
            sample_rate: 采样率
            merge_strategy: 融合策略 ("average" | "weighted" | "replace")
            
        Returns:
            是否成功
        """
        try:
            # 1. 验证说话人是否存在
            existing_embedding = self.voiceprint_db.load_voiceprint(speaker_id)
            if existing_embedding is None:
                log.error(f"[说话人管理] 说话人不存在: {speaker_id}")
                return False
            
            # 2. 验证音频时长
            duration_sec = len(audio) / sample_rate
            if duration_sec < self.min_registration_sec:
                log.error(f"[说话人管理] 音频过短: {duration_sec:.2f}s < {self.min_registration_sec}s")
                return False
            
            # 3. 提取新的声纹特征
            new_embedding = self.sv_engine.embed(audio, sample_rate=sample_rate)
            
            # 4. 评估新声纹质量
            quality_score = self._evaluate_voiceprint_quality(new_embedding, audio, sample_rate)
            if quality_score < self.min_quality_score:
                log.error(f"[说话人管理] 新声纹质量过低: {quality_score:.2f}")
                return False
            
            # 5. 融合声纹
            merged_embedding = self._merge_embeddings(
                existing_embedding, 
                new_embedding, 
                strategy=merge_strategy
            )
            
            # 6. 更新元数据
            metadata = self.voiceprint_db.load_metadata(speaker_id) or {}
            metadata.update({
                "last_updated_at": datetime.now().isoformat(),
                "audio_duration_sec": metadata.get("audio_duration_sec", 0) + duration_sec,
                "quality_score": max(metadata.get("quality_score", 0), quality_score),
                "sample_count": metadata.get("sample_count", 1) + 1,
                "merge_strategy": merge_strategy
            })
            
            # 7. 保存更新后的声纹
            success = self.voiceprint_db.save_voiceprint(
                speaker_id=speaker_id,
                embedding=merged_embedding,
                metadata=metadata
            )
            
            if success:
                log.info(f"[说话人管理] 声纹更新成功: {speaker_id}, 策略={merge_strategy}")
            
            return success
            
        except Exception as e:
            log.error(f"[说话人管理] 声纹更新失败: {type(e).__name__}: {e}")
            return False
    
    def delete_speaker(self, speaker_id: str) -> bool:
        """
        删除说话人
        
        Args:
            speaker_id: 说话人 ID
            
        Returns:
            是否成功
        """
        try:
            # 1. 验证说话人是否存在
            existing_voiceprint = self.voiceprint_db.load_voiceprint(speaker_id)
            if existing_voiceprint is None:
                log.warn(f"[说话人管理] 说话人不存在: {speaker_id}")
                return True  # 幂等操作
            
            # 2. 从声纹数据库删除
            success = self.voiceprint_db.delete(speaker_id)
            
            # 3. 从用户档案数据库删除（如果可用）
            if self.user_profile_db and success:
                try:
                    self._delete_user_profile(speaker_id)
                except Exception as e:
                    log.warn(f"删除用户档案失败: {e}")
            
            if success:
                log.info(f"[说话人管理] 删除成功: {speaker_id}")
            
            return success
            
        except Exception as e:
            log.error(f"[说话人管理] 删除失败: {type(e).__name__}: {e}")
            return False
    
    def list_speakers(self) -> List[SpeakerInfo]:
        """
        列出所有说话人
        
        Returns:
            说话人信息列表
        """
        try:
            speaker_ids = self.voiceprint_db.list_all()
            speakers = []
            
            for speaker_id in speaker_ids:
                speaker_info = self.get_speaker_info(speaker_id)
                if speaker_info:
                    speakers.append(speaker_info)
            
            # 按注册时间排序
            speakers.sort(key=lambda x: x.registered_at, reverse=True)
            
            return speakers
            
        except Exception as e:
            log.error(f"[说话人管理] 列出说话人失败: {type(e).__name__}: {e}")
            return []
    
    def get_speaker_info(self, speaker_id: str) -> Optional[SpeakerInfo]:
        """
        获取说话人详细信息
        
        Args:
            speaker_id: 说话人 ID
            
        Returns:
            说话人信息，如果不存在则返回 None
        """
        try:
            # 1. 检查声纹是否存在
            embedding = self.voiceprint_db.load_voiceprint(speaker_id)
            if embedding is None:
                return None
            
            # 2. 加载元数据
            metadata = self.voiceprint_db.load_metadata(speaker_id)
            if not metadata:
                return None
            
            # 3. 解析时间戳
            registered_at = datetime.fromisoformat(
                metadata.get("registered_at", datetime.now().isoformat())
            )
            last_active_at = datetime.fromisoformat(
                metadata.get("last_active_at", registered_at.isoformat())
            )
            
            # 4. 构造 SpeakerInfo
            return SpeakerInfo(
                speaker_id=speaker_id,
                speaker_name=metadata.get("speaker_name", speaker_id),
                user_id=metadata.get("user_id", speaker_id),
                registered_at=registered_at,
                last_active_at=last_active_at,
                audio_duration_sec=metadata.get("audio_duration_sec", 0.0),
                voiceprint_quality=metadata.get("quality_score", 0.0),
                metadata=metadata
            )
            
        except Exception as e:
            log.error(f"[说话人管理] 获取说话人信息失败: {type(e).__name__}: {e}")
            return None
    
    def _generate_speaker_id(self, speaker_name: str) -> str:
        """
        生成唯一的 speaker_id
        
        Args:
            speaker_name: 说话人名称
            
        Returns:
            唯一的 speaker_id
        """
        # 使用名称 + UUID 确保唯一性
        base_name = "".join(c for c in speaker_name if c.isalnum())[:10]
        unique_suffix = str(uuid.uuid4())[:8]
        return f"speaker_{base_name}_{unique_suffix}"
    
    def _evaluate_voiceprint_quality(
        self, 
        embedding: np.ndarray, 
        audio: np.ndarray, 
        sample_rate: int
    ) -> float:
        """
        评估声纹质量
        
        Args:
            embedding: 声纹向量
            audio: 原始音频
            sample_rate: 采样率
            
        Returns:
            质量评分 (0.0-1.0)
        """
        try:
            # 1. 向量范数检查（归一化后应接近 1.0）
            norm = float(np.linalg.norm(embedding))
            norm_score = min(1.0, norm) if norm > 0 else 0.0
            
            # 2. 音频信噪比估算
            audio_power = float(np.mean(audio ** 2))
            snr_score = min(1.0, audio_power * 1000)  # 简单的功率评估
            
            # 3. 音频时长评分
            duration_sec = len(audio) / sample_rate
            duration_score = min(1.0, duration_sec / 5.0)  # 5秒为满分
            
            # 4. 向量稳定性（检查是否有异常值）
            stability_score = 1.0 - min(1.0, float(np.std(embedding)) / 2.0)
            
            # 5. 综合评分（加权平均）
            quality_score = (
                norm_score * 0.3 +
                snr_score * 0.3 +
                duration_score * 0.2 +
                stability_score * 0.2
            )
            
            return float(np.clip(quality_score, 0.0, 1.0))
            
        except Exception as e:
            log.warn(f"声纹质量评估失败: {e}")
            return 0.5  # 默认中等质量
    
    def _merge_embeddings(
        self, 
        old_embedding: np.ndarray, 
        new_embedding: np.ndarray, 
        strategy: str = "average"
    ) -> np.ndarray:
        """
        融合声纹向量
        
        Args:
            old_embedding: 原有声纹
            new_embedding: 新声纹
            strategy: 融合策略
            
        Returns:
            融合后的声纹向量
        """
        if strategy == "replace":
            return new_embedding
        elif strategy == "weighted":
            # 加权平均（新样本权重较小）
            return 0.7 * old_embedding + 0.3 * new_embedding
        else:  # "average"
            # 简单平均
            merged = (old_embedding + new_embedding) / 2.0
            # 重新归一化
            norm = np.linalg.norm(merged)
            if norm > 0:
                merged = merged / norm
            return merged
    
    def _update_user_profile(self, speaker_id: str, speaker_name: str, metadata: Dict):
        """
        更新用户档案数据库

        Args:
            speaker_id: 说话人 ID
            speaker_name: 说话人名称
            metadata: 元数据
        """
        if self.user_profile_db is None:
            log.debug("UserProfileDatabase 未配置，跳过档案更新: %s", speaker_id)
            return

        try:
            self.user_profile_db.update_profile(
                speaker_id=speaker_id,
                name=speaker_name,
                metadata=metadata,
            )
        except Exception as e:
            log.warn("更新用户档案失败 [%s]: %s", speaker_id, e)

    def _delete_user_profile(self, speaker_id: str):
        """
        删除用户档案

        Args:
            speaker_id: 说话人 ID
        """
        if self.user_profile_db is None:
            log.debug("UserProfileDatabase 未配置，跳过档案删除: %s", speaker_id)
            return

        try:
            self.user_profile_db.delete_profile(speaker_id)
        except Exception as e:
            log.warn("删除用户档案失败 [%s]: %s", speaker_id, e)