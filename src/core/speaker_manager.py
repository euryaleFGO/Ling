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

from src.core.log import log
from src.core.sv_engine import SVEngine
from src.core.voiceprint_database import VoiceprintDatabase


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
        更新用户档案数据库（占位符实现）
        
        Args:
            speaker_id: 说话人 ID
            speaker_name: 说话人名称
            metadata: 元数据
        """
        # TODO: 实现用户档案数据库更新
        # 当 UserProfileDatabase 可用时实现
        pass
    
    def _delete_user_profile(self, speaker_id: str):
        """
        删除用户档案（占位符实现）
        
        Args:
            speaker_id: 说话人 ID
        """
        # TODO: 实现用户档案删除
        # 当 UserProfileDatabase 可用时实现
        pass