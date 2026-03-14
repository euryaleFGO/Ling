"""
上下文构建器
负责将检索结果智能地组织成 LLM 可用的上下文

功能：
1. 去重和冲突检测
2. 按相关性和重要性排序
3. 控制上下文长度
4. 格式化输出
5. 多源融合
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging

from .retriever import RetrievalResult, RetrievalSource
from .query_processor import ProcessedQuery, QueryIntent

logger = logging.getLogger(__name__)


@dataclass
class ContextConfig:
    """上下文配置"""
    max_tokens: int = 2000          # 最大 token 数（估算）
    max_items: int = 10             # 最大条目数
    include_source: bool = True     # 是否包含来源标记
    include_score: bool = False     # 是否包含分数（调试用）
    dedup_threshold: float = 0.8    # 去重阈值
    format_style: str = "natural"   # 格式风格: natural, bullet, structured


class ContextBuilder:
    """
    上下文构建器
    
    将检索结果转换为适合 LLM 使用的上下文字符串
    """
    
    # 不同来源的标签
    SOURCE_LABELS = {
        RetrievalSource.MEMORY: "记忆",
        RetrievalSource.KNOWLEDGE_BASE: "知识库",
        RetrievalSource.KNOWLEDGE_GRAPH: "已知关系",
        RetrievalSource.CONVERSATION: "对话历史",
    }
    
    # 不同意图的上下文前缀
    INTENT_PREFIXES = {
        QueryIntent.RELATION: "关于用户的关系信息：",
        QueryIntent.PREFERENCE: "关于用户的偏好：",
        QueryIntent.FACTUAL: "已知的相关事实：",
        QueryIntent.EVENT: "相关的事件记录：",
        QueryIntent.EMOTION: "用户的情感状态：",
        QueryIntent.KNOWLEDGE: "参考信息：",
        QueryIntent.UNKNOWN: "相关信息：",
    }
    
    def __init__(self, config: Optional[ContextConfig] = None):
        self.config = config or ContextConfig()
    
    def build(
        self,
        results: List[RetrievalResult],
        query: Optional[ProcessedQuery] = None,
        knowledge_graph_context: Optional[str] = None,
        config: Optional[ContextConfig] = None
    ) -> str:
        """
        构建上下文
        
        Args:
            results: 检索结果
            query: 处理后的查询（用于意图感知的格式化）
            knowledge_graph_context: 知识图谱上下文（如果已单独获取）
            config: 配置（覆盖默认配置）
            
        Returns:
            格式化的上下文字符串
        """
        cfg = config or self.config
        
        if not results and not knowledge_graph_context:
            return ""
        
        # 1. 去重
        deduped = self._deduplicate(results, cfg.dedup_threshold)
        
        # 2. 按分数和来源排序
        sorted_results = self._sort_results(deduped, query)
        
        # 3. 截断到最大长度
        truncated = self._truncate(sorted_results, cfg.max_tokens, cfg.max_items)
        
        # 4. 格式化
        formatted = self._format(truncated, query, cfg)
        
        # 5. 添加知识图谱上下文（如果有）
        if knowledge_graph_context:
            formatted = self._merge_kg_context(formatted, knowledge_graph_context)
        
        return formatted
    
    def _deduplicate(
        self,
        results: List[RetrievalResult],
        threshold: float
    ) -> List[RetrievalResult]:
        """
        去重
        
        使用简单的字符串相似度检测重复
        """
        if not results:
            return []
        
        deduped = []
        seen_contents = []
        
        for result in results:
            is_duplicate = False
            
            for seen in seen_contents:
                similarity = self._text_similarity(result.content, seen)
                if similarity >= threshold:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                deduped.append(result)
                seen_contents.append(result.content)
        
        return deduped
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        计算文本相似度（Jaccard 相似度）
        """
        # 简单的字符集相似度
        set1 = set(text1.lower())
        set2 = set(text2.lower())
        
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def _sort_results(
        self,
        results: List[RetrievalResult],
        query: Optional[ProcessedQuery]
    ) -> List[RetrievalResult]:
        """
        排序结果
        
        考虑因素：
        1. 检索分数
        2. 来源优先级
        3. 与查询意图的匹配度
        """
        if not results:
            return []
        
        # 来源优先级（根据意图调整）
        source_priority = {
            RetrievalSource.KNOWLEDGE_GRAPH: 1.2,
            RetrievalSource.MEMORY: 1.0,
            RetrievalSource.KNOWLEDGE_BASE: 0.9,
            RetrievalSource.CONVERSATION: 0.8,
        }
        
        # 根据意图调整优先级
        if query and query.intent:
            if query.intent == QueryIntent.RELATION:
                source_priority[RetrievalSource.KNOWLEDGE_GRAPH] = 1.5
            elif query.intent == QueryIntent.PREFERENCE:
                source_priority[RetrievalSource.MEMORY] = 1.3
            elif query.intent == QueryIntent.KNOWLEDGE:
                source_priority[RetrievalSource.KNOWLEDGE_BASE] = 1.3
        
        # 计算最终排序分数
        def sort_key(r: RetrievalResult) -> float:
            base_score = r.rerank_score if r.rerank_score else r.score
            source_weight = source_priority.get(r.source, 1.0)
            importance = r.metadata.get("importance", 0.5)
            
            return base_score * source_weight * (0.5 + importance * 0.5)
        
        return sorted(results, key=sort_key, reverse=True)
    
    def _truncate(
        self,
        results: List[RetrievalResult],
        max_tokens: int,
        max_items: int
    ) -> List[RetrievalResult]:
        """
        截断到最大长度
        """
        truncated = []
        total_tokens = 0
        
        for result in results:
            if len(truncated) >= max_items:
                break
            
            # 估算 token 数（中文约 2 字符/token）
            content_tokens = len(result.content) // 2 + 10  # +10 for overhead
            
            if total_tokens + content_tokens > max_tokens:
                # 尝试截断内容
                remaining_tokens = max_tokens - total_tokens
                if remaining_tokens > 50:  # 至少保留 50 tokens
                    max_chars = remaining_tokens * 2
                    result.content = result.content[:max_chars] + "..."
                    truncated.append(result)
                break
            
            truncated.append(result)
            total_tokens += content_tokens
        
        return truncated
    
    def _format(
        self,
        results: List[RetrievalResult],
        query: Optional[ProcessedQuery],
        config: ContextConfig
    ) -> str:
        """
        格式化输出
        """
        if not results:
            return ""
        
        # 获取前缀
        prefix = ""
        if query and query.intent in self.INTENT_PREFIXES:
            prefix = self.INTENT_PREFIXES[query.intent]
        else:
            prefix = "相关信息："
        
        # 按格式风格处理
        if config.format_style == "natural":
            return self._format_natural(results, prefix, config)
        elif config.format_style == "bullet":
            return self._format_bullet(results, prefix, config)
        elif config.format_style == "structured":
            return self._format_structured(results, prefix, config)
        else:
            return self._format_natural(results, prefix, config)
    
    def _format_natural(
        self,
        results: List[RetrievalResult],
        prefix: str,
        config: ContextConfig
    ) -> str:
        """自然语言格式"""
        lines = [prefix]
        
        for result in results:
            line = result.content
            
            if config.include_source:
                source_label = self.SOURCE_LABELS.get(result.source, "")
                if source_label:
                    line = f"[{source_label}] {line}"
            
            if config.include_score:
                line = f"{line} (相关度: {result.score:.2f})"
            
            lines.append(f"- {line}")
        
        return "\n".join(lines)
    
    def _format_bullet(
        self,
        results: List[RetrievalResult],
        prefix: str,
        config: ContextConfig
    ) -> str:
        """列表格式"""
        lines = [prefix, ""]
        
        for i, result in enumerate(results, 1):
            line = f"{i}. {result.content}"
            
            if config.include_source:
                source_label = self.SOURCE_LABELS.get(result.source, "")
                if source_label:
                    line = f"{line} [{source_label}]"
            
            lines.append(line)
        
        return "\n".join(lines)
    
    def _format_structured(
        self,
        results: List[RetrievalResult],
        prefix: str,
        config: ContextConfig
    ) -> str:
        """结构化格式（按来源分组）"""
        # 按来源分组
        grouped: Dict[RetrievalSource, List[RetrievalResult]] = {}
        for result in results:
            if result.source not in grouped:
                grouped[result.source] = []
            grouped[result.source].append(result)
        
        lines = [prefix, ""]
        
        for source, items in grouped.items():
            source_label = self.SOURCE_LABELS.get(source, str(source.value))
            lines.append(f"【{source_label}】")
            
            for item in items:
                lines.append(f"  • {item.content}")
            
            lines.append("")
        
        return "\n".join(lines).strip()
    
    def _merge_kg_context(self, context: str, kg_context: str) -> str:
        """合并知识图谱上下文"""
        if not kg_context:
            return context
        
        if not context:
            return kg_context
        
        # 知识图谱放在前面（更重要）
        return f"{kg_context}\n\n{context}"
    
    def build_with_sources(
        self,
        memory_results: List[RetrievalResult] = None,
        kg_results: List[RetrievalResult] = None,
        kb_results: List[RetrievalResult] = None,
        query: Optional[ProcessedQuery] = None
    ) -> str:
        """
        从多个来源构建上下文
        
        Args:
            memory_results: 记忆检索结果
            kg_results: 知识图谱检索结果
            kb_results: 知识库检索结果
            query: 处理后的查询
        """
        all_results = []
        
        if memory_results:
            all_results.extend(memory_results)
        if kg_results:
            all_results.extend(kg_results)
        if kb_results:
            all_results.extend(kb_results)
        
        return self.build(all_results, query)
