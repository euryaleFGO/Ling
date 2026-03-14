"""
RAG Pipeline
整合查询处理、检索和上下文构建的完整流水线

使用方式：
    pipeline = get_rag_pipeline(user_id)
    context = pipeline.retrieve_context("用户喜欢什么？")
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging
import time

from .query_processor import QueryProcessor, ProcessedQuery, QueryIntent
from .retriever import HybridRetriever, RetrievalResult, RetrievalSource
from .context_builder import ContextBuilder, ContextConfig

logger = logging.getLogger(__name__)


@dataclass
class RAGConfig:
    """RAG 配置"""
    # 检索配置
    enable_vector_search: bool = True
    enable_keyword_search: bool = True
    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    top_k: int = 5
    min_score: float = 0.2
    
    # 上下文配置
    max_context_tokens: int = 1500
    max_context_items: int = 8
    include_source: bool = True
    
    # 知识图谱
    enable_knowledge_graph: bool = True
    kg_max_triples: int = 5
    
    # 性能配置
    enable_cache: bool = True
    cache_ttl: int = 300  # 缓存 5 分钟


@dataclass
class RAGResponse:
    """RAG 响应"""
    context: str                           # 构建的上下文
    query: ProcessedQuery                  # 处理后的查询
    results: List[RetrievalResult]         # 检索结果
    kg_context: Optional[str] = None       # 知识图谱上下文
    retrieval_time_ms: float = 0           # 检索耗时
    total_time_ms: float = 0               # 总耗时
    
    def to_dict(self) -> Dict:
        return {
            "context": self.context,
            "intent": self.query.intent.value,
            "result_count": len(self.results),
            "retrieval_time_ms": self.retrieval_time_ms,
            "total_time_ms": self.total_time_ms,
        }


class RAGPipeline:
    """
    RAG 流水线
    
    完整的检索增强生成流程：
    1. 查询预处理（意图识别、关键词提取）
    2. 混合检索（向量 + BM25）
    3. 知识图谱查询
    4. 结果重排序
    5. 上下文构建
    """
    
    def __init__(
        self,
        user_id: str = "default_user",
        config: Optional[RAGConfig] = None
    ):
        self.user_id = user_id
        self.config = config or RAGConfig()
        
        # 初始化组件
        self._query_processor = QueryProcessor()
        self._retriever = HybridRetriever(user_id)
        self._context_builder = ContextBuilder()
        
        # 知识图谱
        self._knowledge_graph = None
        if self.config.enable_knowledge_graph:
            try:
                from ..memory.knowledge_graph import get_knowledge_graph
                self._knowledge_graph = get_knowledge_graph(user_id)
            except Exception as e:
                logger.warning(f"初始化知识图谱失败: {e}")
        
        # 缓存
        self._cache: Dict[str, tuple] = {}  # query -> (response, timestamp)
        
        # 是否已初始化索引
        self._indexed = False
    
    def initialize(self):
        """
        初始化索引
        
        从数据库加载数据到检索器
        """
        if self._indexed:
            return
        
        logger.info("初始化 RAG 索引...")
        
        try:
            # 加载记忆
            self._retriever.load_from_memory_dao()
        except Exception as e:
            logger.warning(f"加载记忆失败: {e}")
        
        try:
            # 加载知识图谱
            self._retriever.load_from_knowledge_graph()
        except Exception as e:
            logger.warning(f"加载知识图谱失败: {e}")
        
        self._indexed = True
        logger.info("RAG 索引初始化完成")
    
    def retrieve_context(
        self,
        query: str,
        config: Optional[RAGConfig] = None
    ) -> RAGResponse:
        """
        检索上下文
        
        Args:
            query: 用户查询
            config: 覆盖默认配置
            
        Returns:
            RAGResponse
        """
        start_time = time.time()
        cfg = config or self.config
        
        # 检查缓存
        if cfg.enable_cache:
            cached = self._get_cached(query)
            if cached:
                return cached
        
        # 确保已初始化
        if not self._indexed:
            self.initialize()
        
        # 1. 查询预处理
        processed_query = self._query_processor.process(query)
        
        # 2. 判断是否需要检索
        if not self._query_processor.should_retrieve(processed_query):
            return RAGResponse(
                context="",
                query=processed_query,
                results=[],
                total_time_ms=(time.time() - start_time) * 1000
            )
        
        # 3. 获取检索配置
        retrieval_config = self._query_processor.get_retrieval_config(processed_query)
        
        # 4. 混合检索
        retrieval_start = time.time()
        
        results = self._retriever.retrieve(
            query=query,
            sources=[RetrievalSource.MEMORY, RetrievalSource.KNOWLEDGE_BASE],
            top_k=retrieval_config.get("top_k", cfg.top_k),
            use_vector=cfg.enable_vector_search,
            use_keyword=cfg.enable_keyword_search,
            vector_weight=cfg.vector_weight,
            keyword_weight=cfg.keyword_weight,
            min_score=cfg.min_score,
        )
        
        # 5. 重排序
        results = self._retriever.rerank(query, results, cfg.top_k)
        
        retrieval_time = (time.time() - retrieval_start) * 1000
        
        # 6. 知识图谱查询
        kg_context = None
        if cfg.enable_knowledge_graph and self._knowledge_graph:
            kg_context = self._query_knowledge_graph(processed_query, cfg.kg_max_triples)
        
        # 7. 构建上下文
        context_config = ContextConfig(
            max_tokens=cfg.max_context_tokens,
            max_items=cfg.max_context_items,
            include_source=cfg.include_source,
        )
        
        context = self._context_builder.build(
            results=results,
            query=processed_query,
            knowledge_graph_context=kg_context,
            config=context_config
        )
        
        # 8. 构建响应
        total_time = (time.time() - start_time) * 1000
        
        response = RAGResponse(
            context=context,
            query=processed_query,
            results=results,
            kg_context=kg_context,
            retrieval_time_ms=retrieval_time,
            total_time_ms=total_time,
        )
        
        # 缓存
        if cfg.enable_cache:
            self._set_cache(query, response)
        
        logger.info(f"RAG 检索完成: 意图={processed_query.intent.value}, "
                   f"结果数={len(results)}, 耗时={total_time:.1f}ms")
        
        return response
    
    def _query_knowledge_graph(
        self,
        query: ProcessedQuery,
        max_triples: int
    ) -> Optional[str]:
        """查询知识图谱"""
        if not self._knowledge_graph:
            return None
        
        try:
            # 如果是关系查询，使用知识图谱推理
            if query.intent == QueryIntent.RELATION:
                inferred = self._knowledge_graph.infer(query.original)
                if inferred:
                    lines = ["已知关系："]
                    for triple in inferred[:max_triples]:
                        lines.append(f"- {triple.to_natural_language()}")
                    return "\n".join(lines)
            
            # 否则返回一般上下文
            return self._knowledge_graph.to_context_string(max_triples=max_triples)
        
        except Exception as e:
            logger.warning(f"知识图谱查询失败: {e}")
            return None
    
    def _get_cached(self, query: str) -> Optional[RAGResponse]:
        """获取缓存"""
        if query in self._cache:
            response, timestamp = self._cache[query]
            if time.time() - timestamp < self.config.cache_ttl:
                logger.debug(f"RAG 缓存命中: {query[:30]}...")
                return response
            else:
                del self._cache[query]
        return None
    
    def _set_cache(self, query: str, response: RAGResponse):
        """设置缓存"""
        self._cache[query] = (response, time.time())
        
        # 清理过期缓存
        if len(self._cache) > 100:
            current_time = time.time()
            expired = [k for k, (_, t) in self._cache.items() 
                      if current_time - t > self.config.cache_ttl]
            for k in expired:
                del self._cache[k]
    
    def add_memory(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict] = None
    ):
        """
        添加记忆到索引
        
        当新记忆被创建时调用
        """
        self._retriever.index_document(
            doc_id=doc_id,
            content=content,
            source=RetrievalSource.MEMORY,
            metadata=metadata
        )
    
    def add_knowledge(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict] = None
    ):
        """添加知识到索引"""
        self._retriever.index_document(
            doc_id=doc_id,
            content=content,
            source=RetrievalSource.KNOWLEDGE_BASE,
            metadata=metadata
        )
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        stats = {
            "user_id": self.user_id,
            "indexed": self._indexed,
            "cache_size": len(self._cache),
            "retriever_stats": self._retriever.get_statistics(),
        }
        
        if self._knowledge_graph:
            stats["knowledge_graph"] = self._knowledge_graph.get_statistics()
        
        return stats
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()


# 全局实例缓存
_pipelines: Dict[str, RAGPipeline] = {}


def get_rag_pipeline(
    user_id: str = "default_user",
    config: Optional[RAGConfig] = None
) -> RAGPipeline:
    """
    获取 RAG 流水线实例
    
    Args:
        user_id: 用户ID
        config: 配置
        
    Returns:
        RAGPipeline 实例
    """
    if user_id not in _pipelines:
        _pipelines[user_id] = RAGPipeline(user_id, config)
    return _pipelines[user_id]
