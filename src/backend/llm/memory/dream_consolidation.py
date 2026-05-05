"""
梦境记忆整合系统 (Dream Consolidation)

灵感来自 OpenClaw 的 Dreaming 功能，自动将短期记忆整合到长期记忆。

三阶段处理:
1. Light 阶段: 筛选和暂存候选记忆
2. Deep 阶段: 评分并提升重要记忆到长期存储
3. REM 阶段: 主题提取和反思

作者: Liying AI System
日期: 2026-04-27
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import json
from pathlib import Path

from .long_term_memory import LongTermMemoryManager
from ..database.conversation_dao import get_conversation_dao
from ..database.memory_dao import get_memory_dao

logger = logging.getLogger(__name__)


class MemoryCandidate:
    """记忆候选"""
    
    def __init__(
        self,
        content: str,
        memory_type: str,
        source_session_id: str,
        created_at: datetime
    ):
        self.content = content
        self.memory_type = memory_type
        self.source_session_id = source_session_id
        self.created_at = created_at
        
        # 评分信号
        self.frequency = 0  # 出现频率
        self.relevance = 0.0  # 相关性
        self.query_diversity = 0  # 查询多样性
        self.recency = 0.0  # 新鲜度
        self.consolidation = 0  # 整合度（多日重复）
        self.conceptual_richness = 0.0  # 概念丰富度
        
        # 最终得分
        self.score = 0.0
    
    def calculate_score(self) -> float:
        """
        计算综合得分
        
        权重参考 OpenClaw:
        - 频率: 0.24
        - 相关性: 0.30
        - 查询多样性: 0.15
        - 新鲜度: 0.15
        - 整合度: 0.10
        - 概念丰富度: 0.06
        """
        self.score = (
            self.frequency * 0.24 +
            self.relevance * 0.30 +
            self.query_diversity * 0.15 +
            self.recency * 0.15 +
            self.consolidation * 0.10 +
            self.conceptual_richness * 0.06
        )
        return self.score
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "content": self.content,
            "type": self.memory_type,
            "source_session_id": self.source_session_id,
            "created_at": self.created_at.isoformat(),
            "signals": {
                "frequency": self.frequency,
                "relevance": self.relevance,
                "query_diversity": self.query_diversity,
                "recency": self.recency,
                "consolidation": self.consolidation,
                "conceptual_richness": self.conceptual_richness
            },
            "score": self.score
        }


class DreamConsolidation:
    """梦境记忆整合系统"""
    
    def __init__(
        self,
        user_id: str = "default_user",
        dream_dir: Optional[Path] = None
    ):
        self.user_id = user_id
        self.dream_dir = dream_dir or Path("data/dreams")
        self.dream_dir.mkdir(parents=True, exist_ok=True)
        
        self.ltm_manager = LongTermMemoryManager(user_id)
        self.conversation_dao = get_conversation_dao()
        self.memory_dao = get_memory_dao()
        
        # 候选记忆池
        self.candidates: List[MemoryCandidate] = []
        
        # 梦境日记
        self.dream_diary_path = self.dream_dir / "DREAMS.md"
        
    def run_full_cycle(self, days_back: int = 7) -> Dict[str, Any]:
        """
        运行完整的梦境周期
        
        Args:
            days_back: 回溯天数
            
        Returns:
            处理结果统计
        """
        logger.info(f"[梦境] 开始记忆整合周期 (用户: {self.user_id}, 回溯: {days_back}天)")
        
        start_time = datetime.now()
        
        # 阶段 1: Light - 筛选候选
        light_result = self.phase_light(days_back)
        
        # 阶段 2: Deep - 评分和提升
        deep_result = self.phase_deep()
        
        # 阶段 3: REM - 主题反思
        rem_result = self.phase_rem()
        
        # 记录梦境日记
        self.write_dream_diary(light_result, deep_result, rem_result)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        result = {
            "user_id": self.user_id,
            "timestamp": start_time.isoformat(),
            "duration_seconds": duration,
            "light": light_result,
            "deep": deep_result,
            "rem": rem_result
        }
        
        logger.info(f"[梦境] 整合周期完成 (耗时: {duration:.2f}s)")
        return result
    
    def phase_light(self, days_back: int = 7) -> Dict[str, Any]:
        """
        Light 阶段: 筛选和暂存候选记忆
        
        从最近的对话中提取潜在的长期记忆候选
        """
        logger.info("[梦境-Light] 开始筛选候选记忆...")
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # 获取最近的会话
        # 注意：这里需要 conversation_dao 支持按日期查询
        # 简化实现：获取最近的 N 个会话
        recent_sessions = self._get_recent_sessions(days_back)
        
        candidates = []
        
        for session in recent_sessions:
            session_id = session["session_id"]
            messages = session.get("messages", [])
            
            # 分析对话，提取候选记忆
            extracted = self._extract_memory_candidates(session_id, messages)
            candidates.extend(extracted)
        
        # 去重和初步筛选
        candidates = self._deduplicate_candidates(candidates)
        
        # 计算初步信号
        for candidate in candidates:
            self._calculate_light_signals(candidate)
        
        self.candidates = candidates
        
        logger.info(f"[梦境-Light] 筛选完成，候选数: {len(candidates)}")
        
        return {
            "phase": "light",
            "candidates_count": len(candidates),
            "sessions_analyzed": len(recent_sessions)
        }
    
    def phase_deep(self, promotion_threshold: float = 0.6) -> Dict[str, Any]:
        """
        Deep 阶段: 评分并提升重要记忆
        
        Args:
            promotion_threshold: 提升阈值（得分 >= 此值才提升）
        """
        logger.info("[梦境-Deep] 开始评分和提升...")
        
        if not self.candidates:
            logger.warning("[梦境-Deep] 没有候选记忆")
            return {"phase": "deep", "promoted_count": 0}
        
        # 计算完整评分
        for candidate in self.candidates:
            self._calculate_deep_signals(candidate)
            candidate.calculate_score()
        
        # 按得分排序
        self.candidates.sort(key=lambda c: c.score, reverse=True)
        
        # 提升高分记忆到长期存储
        promoted = []
        for candidate in self.candidates:
            if candidate.score >= promotion_threshold:
                memory_id = self.ltm_manager.add_memory(
                    content=candidate.content,
                    memory_type=candidate.memory_type,
                    importance=candidate.score,  # 使用得分作为重要性
                    source_session_id=candidate.source_session_id,
                    tags=["dream_promoted"]
                )
                promoted.append({
                    "memory_id": memory_id,
                    "content": candidate.content[:100],
                    "score": candidate.score
                })
        
        logger.info(f"[梦境-Deep] 提升完成，提升数: {len(promoted)}/{len(self.candidates)}")
        
        return {
            "phase": "deep",
            "candidates_scored": len(self.candidates),
            "promoted_count": len(promoted),
            "promoted_memories": promoted,
            "threshold": promotion_threshold
        }
    
    def phase_rem(self) -> Dict[str, Any]:
        """
        REM 阶段: 主题提取和反思
        
        分析提升的记忆，提取主题和模式
        """
        logger.info("[梦境-REM] 开始主题反思...")
        
        if not self.candidates:
            return {"phase": "rem", "themes": []}
        
        # 提取主题（简化实现：基于记忆类型和内容关键词）
        themes = self._extract_themes(self.candidates)
        
        # 识别重复模式
        patterns = self._identify_patterns(self.candidates)
        
        logger.info(f"[梦境-REM] 反思完成，主题数: {len(themes)}")
        
        return {
            "phase": "rem",
            "themes": themes,
            "patterns": patterns
        }
    
    def _get_recent_sessions(self, days_back: int) -> List[Dict]:
        """获取最近的会话"""
        # 简化实现：获取用户的最近 N 个会话
        # 实际应该按日期过滤
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # 这里需要 conversation_dao 支持按日期查询
        # 暂时返回空列表，实际使用时需要实现
        return []
    
    def _extract_memory_candidates(
        self,
        session_id: str,
        messages: List[Dict]
    ) -> List[MemoryCandidate]:
        """从对话中提取记忆候选"""
        candidates = []
        
        # 简化实现：提取用户的重要陈述
        # 实际应该使用 LLM 或规则引擎
        
        for msg in messages:
            if msg.get("role") != "user":
                continue
            
            content = msg.get("content", "")
            
            # 简单规则：包含特定关键词的消息
            keywords = ["喜欢", "讨厌", "想要", "希望", "记住", "重要"]
            if any(kw in content for kw in keywords):
                candidate = MemoryCandidate(
                    content=content,
                    memory_type="preference",  # 简化分类
                    source_session_id=session_id,
                    created_at=msg.get("timestamp", datetime.utcnow())
                )
                candidates.append(candidate)
        
        return candidates
    
    def _deduplicate_candidates(
        self,
        candidates: List[MemoryCandidate]
    ) -> List[MemoryCandidate]:
        """去重候选记忆"""
        # 简化实现：基于内容相似度去重
        # 实际应该使用向量相似度
        
        seen = set()
        unique = []
        
        for candidate in candidates:
            # 简单的内容哈希
            content_hash = hash(candidate.content[:100])
            if content_hash not in seen:
                seen.add(content_hash)
                unique.append(candidate)
        
        return unique
    
    def _calculate_light_signals(self, candidate: MemoryCandidate):
        """计算 Light 阶段的信号"""
        # 频率：简化为 1（实际应该统计出现次数）
        candidate.frequency = 1.0
        
        # 新鲜度：基于时间衰减
        days_old = (datetime.utcnow() - candidate.created_at).days
        candidate.recency = max(0, 1.0 - days_old / 30.0)  # 30 天衰减到 0
    
    def _calculate_deep_signals(self, candidate: MemoryCandidate):
        """计算 Deep 阶段的完整信号"""
        # 相关性：简化为固定值（实际应该基于检索质量）
        candidate.relevance = 0.7
        
        # 查询多样性：简化为固定值
        candidate.query_diversity = 0.5
        
        # 整合度：简化为固定值（实际应该统计多日重复）
        candidate.consolidation = 0.3
        
        # 概念丰富度：基于内容长度和复杂度
        content_length = len(candidate.content)
        candidate.conceptual_richness = min(1.0, content_length / 200.0)
    
    def _extract_themes(self, candidates: List[MemoryCandidate]) -> List[Dict]:
        """提取主题"""
        # 简化实现：基于记忆类型统计
        type_counts = Counter(c.memory_type for c in candidates)
        
        themes = []
        for mem_type, count in type_counts.most_common():
            themes.append({
                "theme": mem_type,
                "count": count,
                "percentage": count / len(candidates) * 100
            })
        
        return themes
    
    def _identify_patterns(self, candidates: List[MemoryCandidate]) -> List[str]:
        """识别重复模式"""
        # 简化实现：返回空列表
        # 实际应该使用 NLP 技术识别模式
        return []
    
    def write_dream_diary(
        self,
        light_result: Dict,
        deep_result: Dict,
        rem_result: Dict
    ):
        """写入梦境日记"""
        now = datetime.now()
        
        entry = f"""
## 梦境记录 - {now.strftime('%Y-%m-%d %H:%M')}

### Light 阶段
- 分析会话数: {light_result.get('sessions_analyzed', 0)}
- 候选记忆数: {light_result.get('candidates_count', 0)}

### Deep 阶段
- 评分记忆数: {deep_result.get('candidates_scored', 0)}
- 提升记忆数: {deep_result.get('promoted_count', 0)}
- 提升阈值: {deep_result.get('threshold', 0)}

### REM 阶段
- 识别主题数: {len(rem_result.get('themes', []))}

### 提升的记忆
"""
        
        for mem in deep_result.get('promoted_memories', []):
            entry += f"- [{mem['score']:.2f}] {mem['content']}\n"
        
        entry += "\n---\n"
        
        # 追加到日记文件
        with open(self.dream_diary_path, 'a', encoding='utf-8') as f:
            f.write(entry)
        
        logger.info(f"[梦境] 日记已更新: {self.dream_diary_path}")


def run_dream_consolidation(user_id: str = "default_user", days_back: int = 7) -> Dict:
    """
    运行梦境整合（便捷函数）
    
    Args:
        user_id: 用户 ID
        days_back: 回溯天数
        
    Returns:
        处理结果
    """
    dream = DreamConsolidation(user_id)
    return dream.run_full_cycle(days_back)


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    result = run_dream_consolidation()
    logger.debug(json.dumps(result, indent=2, ensure_ascii=False))
