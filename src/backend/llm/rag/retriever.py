"""
混合检索器
支持向量检索 + BM25 关键词检索 + 结果融合

特性：
1. 向量语义检索（ChromaDB）
2. BM25 关键词检索
3. 结果融合（RRF: Reciprocal Rank Fusion）
4. 多源检索（记忆、知识库、知识图谱）
5. 重排序和过滤
"""
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import math
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class RetrievalSource(Enum):
    """检索源"""
    MEMORY = "memory"
    KNOWLEDGE_BASE = "knowledge_base"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    CONVERSATION = "conversation"


@dataclass
class RetrievalResult:
    """检索结果"""
    doc_id: str
    content: str
    source: RetrievalSource
    score: float
    metadata: Dict = field(default_factory=dict)
    
    # 检索细节
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    rerank_score: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "source": self.source.value,
            "score": self.score,
            "metadata": self.metadata,
        }


class BM25:
    """
    BM25 关键词检索算法
    
    用于快速的关键词匹配检索
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Args:
            k1: 词频饱和参数
            b: 文档长度归一化参数
        """
        self.k1 = k1
        self.b = b
        self._documents: Dict[str, str] = {}  # doc_id -> content
        self._doc_lengths: Dict[str, int] = {}
        self._avg_doc_length: float = 0
        self._term_freqs: Dict[str, Dict[str, int]] = defaultdict(dict)  # term -> {doc_id: freq}
        self._doc_freqs: Dict[str, int] = defaultdict(int)  # term -> doc_count
        self._total_docs: int = 0
    
    def add_document(self, doc_id: str, content: str):
        """添加文档"""
        if doc_id in self._documents:
            return
        
        self._documents[doc_id] = content
        
        # 分词（简单实现）
        terms = self._tokenize(content)
        self._doc_lengths[doc_id] = len(terms)
        
        # 统计词频
        term_count = defaultdict(int)
        for term in terms:
            term_count[term] += 1
        
        # 更新索引
        for term, freq in term_count.items():
            self._term_freqs[term][doc_id] = freq
            if freq > 0:
                self._doc_freqs[term] += 1
        
        self._total_docs += 1
        self._avg_doc_length = sum(self._doc_lengths.values()) / max(self._total_docs, 1)
    
    def add_documents(self, documents: Dict[str, str]):
        """批量添加文档"""
        for doc_id, content in documents.items():
            self.add_document(doc_id, content)
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        搜索
        
        Returns:
            [(doc_id, score), ...]
        """
        if not self._documents:
            return []
        
        query_terms = self._tokenize(query)
        
        scores = defaultdict(float)
        
        for term in query_terms:
            if term not in self._term_freqs:
                continue
            
            # IDF
            df = self._doc_freqs[term]
            idf = math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1)
            
            for doc_id, tf in self._term_freqs[term].items():
                doc_len = self._doc_lengths[doc_id]
                # BM25 公式
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self._avg_doc_length)
                scores[doc_id] += idf * numerator / denominator
        
        # 排序
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]
    
    def _tokenize(self, text: str) -> List[str]:
        """简单分词"""
        import re
        
        # 中文：按字符
        chinese = re.findall(r'[\u4e00-\u9fff]', text)
        
        # 中文 bigram
        chinese_bigrams = []
        for i in range(len(chinese) - 1):
            chinese_bigrams.append(chinese[i] + chinese[i+1])
        
        # 英文：按单词
        english = re.findall(r'[a-zA-Z]+', text.lower())
        
        return chinese + chinese_bigrams + english
    
    def clear(self):
        """清空索引"""
        self._documents.clear()
        self._doc_lengths.clear()
        self._term_freqs.clear()
        self._doc_freqs.clear()
        self._total_docs = 0
        self._avg_doc_length = 0


class HybridRetriever:
    """
    混合检索器
    
    结合向量检索和 BM25 检索，支持多源数据
    """
    
    def __init__(self, user_id: str = "default_user"):
        self.user_id = user_id
        
        # BM25 索引（每个源一个）
        self._bm25_indexes: Dict[RetrievalSource, BM25] = {
            RetrievalSource.MEMORY: BM25(),
            RetrievalSource.KNOWLEDGE_BASE: BM25(),
            RetrievalSource.KNOWLEDGE_GRAPH: BM25(),
        }
        
        # 文档缓存
        self._doc_cache: Dict[str, Dict] = {}
        
        # 初始化向量存储
        self._vector_stores = {}
        self._init_vector_stores()
    
    def _init_vector_stores(self):
        """初始化向量存储"""
        try:
            from ..database.chroma_client import MemoryVectorStore, KnowledgeVectorStore
            self._vector_stores[RetrievalSource.MEMORY] = MemoryVectorStore()
            self._vector_stores[RetrievalSource.KNOWLEDGE_BASE] = KnowledgeVectorStore()
        except Exception as e:
            logger.warning(f"初始化向量存储失败: {e}")
    
    def index_document(
        self,
        doc_id: str,
        content: str,
        source: RetrievalSource,
        metadata: Optional[Dict] = None
    ):
        """
        索引文档
        
        同时添加到 BM25 索引和向量存储
        """
        # 添加到 BM25
        if source in self._bm25_indexes:
            self._bm25_indexes[source].add_document(doc_id, content)
        
        # 缓存文档
        self._doc_cache[doc_id] = {
            "content": content,
            "source": source,
            "metadata": metadata or {}
        }
        
        # 添加到向量存储
        if source in self._vector_stores:
            try:
                self._vector_stores[source].add(
                    doc_id=doc_id,
                    text=content,
                    metadata={"user_id": self.user_id, **(metadata or {})}
                )
            except Exception as e:
                logger.warning(f"添加到向量存储失败: {e}")
    
    def retrieve(
        self,
        query: str,
        sources: Optional[List[RetrievalSource]] = None,
        top_k: int = 5,
        use_vector: bool = True,
        use_keyword: bool = True,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        min_score: float = 0.0,
        where: Optional[Dict] = None
    ) -> List[RetrievalResult]:
        """
        混合检索
        
        Args:
            query: 查询文本
            sources: 检索源列表
            top_k: 返回数量
            use_vector: 是否使用向量检索
            use_keyword: 是否使用关键词检索
            vector_weight: 向量检索权重
            keyword_weight: 关键词检索权重
            min_score: 最小分数阈值
            where: 元数据过滤条件
            
        Returns:
            检索结果列表
        """
        if sources is None:
            sources = [RetrievalSource.MEMORY, RetrievalSource.KNOWLEDGE_BASE]
        
        all_results: Dict[str, RetrievalResult] = {}
        
        for source in sources:
            # 向量检索
            vector_results = {}
            if use_vector and source in self._vector_stores:
                vector_results = self._vector_retrieve(query, source, top_k * 2, where)
            
            # BM25 检索
            keyword_results = {}
            if use_keyword and source in self._bm25_indexes:
                keyword_results = self._keyword_retrieve(query, source, top_k * 2)
            
            # 融合结果（RRF）
            fused = self._fuse_results(
                vector_results,
                keyword_results,
                vector_weight,
                keyword_weight
            )
            
            # 创建 RetrievalResult 对象
            for doc_id, score_info in fused.items():
                if doc_id in self._doc_cache:
                    doc = self._doc_cache[doc_id]
                    result = RetrievalResult(
                        doc_id=doc_id,
                        content=doc["content"],
                        source=source,
                        score=score_info["fused_score"],
                        metadata=doc.get("metadata", {}),
                        vector_score=score_info.get("vector_score"),
                        keyword_score=score_info.get("keyword_score"),
                    )
                    
                    # 如果已存在，保留分数更高的
                    if doc_id not in all_results or all_results[doc_id].score < result.score:
                        all_results[doc_id] = result
        
        # 排序并过滤
        results = sorted(all_results.values(), key=lambda x: x.score, reverse=True)
        results = [r for r in results if r.score >= min_score]
        
        return results[:top_k]
    
    def _vector_retrieve(
        self,
        query: str,
        source: RetrievalSource,
        top_k: int,
        where: Optional[Dict] = None
    ) -> Dict[str, float]:
        """向量检索"""
        results = {}
        
        try:
            store = self._vector_stores.get(source)
            if not store:
                return results
            
            # 构建过滤条件
            filter_where = {"user_id": self.user_id}
            if where:
                filter_where.update(where)
            
            # 检索
            response = store.query(
                query_text=query,
                n_results=top_k,
                where=filter_where
            )
            
            if response and response.get("ids") and response["ids"][0]:
                ids = response["ids"][0]
                distances = response["distances"][0] if response.get("distances") else [0] * len(ids)
                
                for doc_id, distance in zip(ids, distances):
                    # 将距离转换为相似度分数 (余弦距离)
                    # ChromaDB 默认使用 L2 距离，转换为 0-1 的相似度
                    score = 1 / (1 + distance)
                    results[doc_id] = score
        
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
        
        return results
    
    def _keyword_retrieve(
        self,
        query: str,
        source: RetrievalSource,
        top_k: int
    ) -> Dict[str, float]:
        """BM25 关键词检索"""
        results = {}
        
        try:
            bm25 = self._bm25_indexes.get(source)
            if not bm25:
                return results
            
            search_results = bm25.search(query, top_k)
            
            # 归一化分数到 0-1
            if search_results:
                max_score = max(r[1] for r in search_results)
                if max_score > 0:
                    for doc_id, score in search_results:
                        results[doc_id] = score / max_score
        
        except Exception as e:
            logger.warning(f"BM25 检索失败: {e}")
        
        return results
    
    def _fuse_results(
        self,
        vector_results: Dict[str, float],
        keyword_results: Dict[str, float],
        vector_weight: float,
        keyword_weight: float
    ) -> Dict[str, Dict]:
        """
        融合检索结果
        
        使用 RRF (Reciprocal Rank Fusion) 算法
        """
        fused = {}
        k = 60  # RRF 参数
        
        # 计算 RRF 分数
        # 向量检索排名
        vector_ranks = {doc_id: rank + 1 for rank, (doc_id, _) in 
                       enumerate(sorted(vector_results.items(), key=lambda x: x[1], reverse=True))}
        
        # 关键词检索排名
        keyword_ranks = {doc_id: rank + 1 for rank, (doc_id, _) in 
                        enumerate(sorted(keyword_results.items(), key=lambda x: x[1], reverse=True))}
        
        # 所有文档
        all_docs = set(vector_results.keys()) | set(keyword_results.keys())
        
        for doc_id in all_docs:
            vector_score = vector_results.get(doc_id, 0)
            keyword_score = keyword_results.get(doc_id, 0)
            
            # RRF 分数
            vector_rrf = 1 / (k + vector_ranks.get(doc_id, 1000)) if doc_id in vector_ranks else 0
            keyword_rrf = 1 / (k + keyword_ranks.get(doc_id, 1000)) if doc_id in keyword_ranks else 0
            
            # 加权融合
            fused_score = (vector_weight * vector_rrf + keyword_weight * keyword_rrf)
            
            # 也考虑原始分数
            weighted_score = (vector_weight * vector_score + keyword_weight * keyword_score)
            
            # 最终分数 = RRF + 原始分数的组合
            final_score = 0.5 * fused_score + 0.5 * weighted_score
            
            fused[doc_id] = {
                "fused_score": final_score,
                "vector_score": vector_score,
                "keyword_score": keyword_score,
                "vector_rank": vector_ranks.get(doc_id),
                "keyword_rank": keyword_ranks.get(doc_id),
            }
        
        return fused
    
    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """
        重排序
        
        基于额外信号重新排序结果：
        1. 内容长度（适中长度优先）
        2. 元数据（如重要性、时间）
        3. 与查询的词汇重叠度
        """
        for result in results:
            rerank_score = result.score
            
            # 1. 内容长度因子（100-500 字符为最佳）
            content_len = len(result.content)
            if 50 <= content_len <= 500:
                length_factor = 1.0
            elif content_len < 50:
                length_factor = content_len / 50
            else:
                length_factor = 500 / content_len
            
            # 2. 重要性因子
            importance = result.metadata.get("importance", 0.5)
            importance_factor = 0.5 + importance * 0.5
            
            # 3. 词汇重叠度
            query_words = set(query.lower())
            content_words = set(result.content.lower())
            overlap = len(query_words & content_words) / max(len(query_words), 1)
            overlap_factor = 0.8 + overlap * 0.2
            
            # 综合重排序分数
            result.rerank_score = rerank_score * length_factor * importance_factor * overlap_factor
        
        # 按重排序分数排序
        results.sort(key=lambda x: x.rerank_score or x.score, reverse=True)
        
        if top_k:
            results = results[:top_k]
        
        return results
    
    def load_from_memory_dao(self):
        """从 MemoryDAO 加载数据到索引"""
        try:
            from ..database.memory_dao import get_memory_dao
            dao = get_memory_dao()
            
            # 获取所有记忆
            memories = dao.get_recent_memories(user_id=self.user_id, limit=1000)
            
            for mem in memories:
                self.index_document(
                    doc_id=mem["memory_id"],
                    content=mem["content"],
                    source=RetrievalSource.MEMORY,
                    metadata={
                        "type": mem.get("type"),
                        "importance": mem.get("importance", 0.5),
                        "tags": mem.get("tags", []),
                    }
                )
            
            logger.info(f"从 MemoryDAO 加载了 {len(memories)} 条记忆")
        
        except Exception as e:
            logger.warning(f"加载记忆数据失败: {e}")
    
    def load_from_knowledge_graph(self):
        """从知识图谱加载数据"""
        try:
            from ..memory.knowledge_graph import get_knowledge_graph
            kg = get_knowledge_graph(self.user_id)
            
            # 将三元组转换为文档
            for triple in kg._triples:
                doc_id = f"kg_{triple.subject.name}_{triple.relation.relation_type}_{triple.obj.name}"
                content = triple.to_natural_language()
                
                self.index_document(
                    doc_id=doc_id,
                    content=content,
                    source=RetrievalSource.KNOWLEDGE_GRAPH,
                    metadata={
                        "subject": triple.subject.name,
                        "relation": triple.relation.relation_type,
                        "object": triple.obj.name,
                        "confidence": triple.confidence,
                    }
                )
            
            logger.info(f"从知识图谱加载了 {len(kg._triples)} 条三元组")
        
        except Exception as e:
            logger.warning(f"加载知识图谱数据失败: {e}")
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        stats = {}
        for source, bm25 in self._bm25_indexes.items():
            stats[source.value] = {
                "doc_count": bm25._total_docs,
                "avg_doc_length": bm25._avg_doc_length,
            }
        stats["total_cached"] = len(self._doc_cache)
        return stats
