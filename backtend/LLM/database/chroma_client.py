"""
Chroma 向量数据库客户端
用于 RAG 检索
"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 模型目录
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
# Embedding 模型目录
EMBEDDING_MODEL_DIR = os.path.join(MODELS_DIR, "embedding")

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class LocalONNXMiniLM(ONNXMiniLM_L6_V2):
    """使用本地模型路径的 ONNX Embedding 函数"""
    
    # 覆盖默认路径，使用项目内的模型目录
    DOWNLOAD_PATH = Path(EMBEDDING_MODEL_DIR) / "all-MiniLM-L6-v2"


class ChromaClient:
    """Chroma 向量数据库客户端"""
    
    _instance: Optional['ChromaClient'] = None
    _client: Optional[chromadb.Client] = None
    _embedding_function = None
    
    # Collection 名称
    KNOWLEDGE_COLLECTION = "knowledge_vectors"
    MEMORY_COLLECTION = "memory_vectors"
    CONVERSATION_COLLECTION = "conversation_vectors"
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, persist_directory: str = None):
        if self._client is None:
            # 默认持久化到项目目录
            if persist_directory is None:
                persist_directory = os.path.join(
                    os.path.dirname(__file__), 
                    "..", 
                    "chroma_data"
                )
            
            self._persist_dir = os.path.abspath(persist_directory)
            os.makedirs(self._persist_dir, exist_ok=True)
            
            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=Settings(anonymized_telemetry=False)
            )
            
            # 初始化本地 embedding 模型
            self._embedding_function = LocalONNXMiniLM(
                preferred_providers=["CPUExecutionProvider"]
            )
            
            logger.info(f"Chroma 初始化成功: {self._persist_dir}")
            logger.info(f"Embedding 模型路径: {LocalONNXMiniLM.DOWNLOAD_PATH}")
    
    @property
    def client(self) -> chromadb.Client:
        return self._client
    
    @property
    def embedding_function(self):
        """获取 embedding 函数"""
        return self._embedding_function
    
    def get_or_create_collection(
        self, 
        name: str,
        embedding_function=None
    ) -> chromadb.Collection:
        """获取或创建集合"""
        # 默认使用本地 embedding 函数
        ef = embedding_function or self._embedding_function
        return self._client.get_or_create_collection(
            name=name,
            embedding_function=ef
        )
    
    def get_knowledge_collection(self) -> chromadb.Collection:
        """获取知识库集合"""
        return self.get_or_create_collection(self.KNOWLEDGE_COLLECTION)
    
    def get_memory_collection(self) -> chromadb.Collection:
        """获取记忆集合"""
        return self.get_or_create_collection(self.MEMORY_COLLECTION)
    
    def get_conversation_collection(self) -> chromadb.Collection:
        """获取对话集合"""
        return self.get_or_create_collection(self.CONVERSATION_COLLECTION)


# 全局实例
_chroma_client: Optional[ChromaClient] = None


def get_chroma_client(persist_directory: str = None) -> ChromaClient:
    """获取 Chroma 客户端实例"""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = ChromaClient(persist_directory)
    return _chroma_client


class VectorStore:
    """向量存储操作封装"""
    
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self._collection = None
    
    @property
    def collection(self) -> chromadb.Collection:
        if self._collection is None:
            client = get_chroma_client()
            self._collection = client.get_or_create_collection(self.collection_name)
        return self._collection
    
    def add(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict] = None,
        embedding: Optional[List[float]] = None
    ):
        """
        添加文档到向量库
        
        Args:
            doc_id: 文档ID (与 MongoDB 关联)
            text: 文本内容
            metadata: 元数据
            embedding: 预计算的向量 (可选，不提供则自动计算)
        """
        add_kwargs = {
            "ids": [doc_id],
            "documents": [text],
            "metadatas": [metadata or {}]
        }
        
        if embedding:
            add_kwargs["embeddings"] = [embedding]
        
        self.collection.add(**add_kwargs)
    
    def add_batch(
        self,
        doc_ids: List[str],
        texts: List[str],
        metadatas: Optional[List[Dict]] = None,
        embeddings: Optional[List[List[float]]] = None
    ):
        """批量添加文档"""
        add_kwargs = {
            "ids": doc_ids,
            "documents": texts,
            "metadatas": metadatas or [{} for _ in doc_ids]
        }
        
        if embeddings:
            add_kwargs["embeddings"] = embeddings
        
        self.collection.add(**add_kwargs)
    
    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict] = None,
        where_document: Optional[Dict] = None
    ) -> Dict:
        """
        查询相似文档
        
        Args:
            query_text: 查询文本
            n_results: 返回数量
            where: 元数据过滤条件
            where_document: 文档内容过滤条件
            
        Returns:
            查询结果 {ids, documents, metadatas, distances}
        """
        query_kwargs = {
            "query_texts": [query_text],
            "n_results": n_results
        }
        
        if where:
            query_kwargs["where"] = where
        if where_document:
            query_kwargs["where_document"] = where_document
        
        return self.collection.query(**query_kwargs)
    
    def query_by_embedding(
        self,
        embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict] = None
    ) -> Dict:
        """通过向量查询"""
        query_kwargs = {
            "query_embeddings": [embedding],
            "n_results": n_results
        }
        
        if where:
            query_kwargs["where"] = where
        
        return self.collection.query(**query_kwargs)
    
    def update(
        self,
        doc_id: str,
        text: Optional[str] = None,
        metadata: Optional[Dict] = None,
        embedding: Optional[List[float]] = None
    ):
        """更新文档"""
        update_kwargs = {"ids": [doc_id]}
        
        if text:
            update_kwargs["documents"] = [text]
        if metadata:
            update_kwargs["metadatas"] = [metadata]
        if embedding:
            update_kwargs["embeddings"] = [embedding]
        
        self.collection.update(**update_kwargs)
    
    def delete(self, doc_ids: List[str]):
        """删除文档"""
        self.collection.delete(ids=doc_ids)
    
    def get(self, doc_ids: List[str]) -> Dict:
        """获取文档"""
        return self.collection.get(ids=doc_ids)
    
    def count(self) -> int:
        """获取文档数量"""
        return self.collection.count()


# 预定义的向量存储
class KnowledgeVectorStore(VectorStore):
    """知识库向量存储"""
    def __init__(self):
        super().__init__(ChromaClient.KNOWLEDGE_COLLECTION)


class MemoryVectorStore(VectorStore):
    """记忆向量存储"""
    def __init__(self):
        super().__init__(ChromaClient.MEMORY_COLLECTION)


class ConversationVectorStore(VectorStore):
    """对话向量存储"""
    def __init__(self):
        super().__init__(ChromaClient.CONVERSATION_COLLECTION)
