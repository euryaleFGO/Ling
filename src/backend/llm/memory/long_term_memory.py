"""
长期记忆管理器
管理和检索长期记忆
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from ..database.memory_dao import get_memory_dao, MemoryDAO
from ..database.chroma_client import MemoryVectorStore

logger = logging.getLogger(__name__)


class LongTermMemoryManager:
    """
    长期记忆管理器
    
    职责:
    1. 存储长期记忆到 MongoDB + Chroma
    2. 检索相关记忆 (语义搜索)
    3. 管理记忆的重要性和生命周期
    """
    
    def __init__(self, user_id: str = "default_user"):
        self.user_id = user_id
        self._memory_dao: MemoryDAO = get_memory_dao()
        self._vector_store = MemoryVectorStore()
    
    def add_memory(
        self,
        content: str,
        memory_type: str,
        importance: float = 0.5,
        source_session_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        添加长期记忆
        
        Args:
            content: 记忆内容
            memory_type: 类型 (fact | event | preference | emotion | summary)
            importance: 重要程度 (0-1)
            source_session_id: 来源会话
            tags: 标签
            
        Returns:
            memory_id
        """
        # 1. 存入 MongoDB
        memory_id = self._memory_dao.add_memory(
            content=content,
            memory_type=memory_type,
            user_id=self.user_id,
            importance=importance,
            source_session_id=source_session_id,
            tags=tags
        )
        
        # 2. 存入 Chroma 向量库
        self._vector_store.add(
            doc_id=memory_id,
            text=content,
            metadata={
                "user_id": self.user_id,
                "type": memory_type,
                "importance": importance,
                "tags": ",".join(tags) if tags else ""
            }
        )
        
        logger.info(f"添加长期记忆: {memory_id} - {content[:50]}...")
        return memory_id
    
    def search_relevant_memories(
        self,
        query: str,
        n_results: int = 5,
        min_importance: float = 0.0,
        memory_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        搜索相关记忆 (语义搜索)
        
        Args:
            query: 查询文本
            n_results: 返回数量
            min_importance: 最小重要程度
            memory_types: 限制记忆类型
            
        Returns:
            相关记忆列表
        """
        # Chroma 的 where 过滤只支持简单条件，复杂过滤在结果中处理
        where = {"user_id": self.user_id}
        
        # 从 Chroma 检索
        results = self._vector_store.query(
            query_text=query,
            n_results=n_results * 2,  # 多检索一些，后面再过滤
            where=where
        )
        
        if not results or not results.get("ids") or not results["ids"][0]:
            return []
        
        # 获取详细信息
        memories = []
        for i, doc_id in enumerate(results["ids"][0]):
            memory = self._memory_dao.get_memory(doc_id)
            if memory:
                # 过滤类型
                if memory_types and memory.get("type") not in memory_types:
                    continue
                # 过滤重要程度
                if memory.get("importance", 0) < min_importance:
                    continue
                
                memory["_distance"] = results["distances"][0][i] if results.get("distances") else None
                memories.append(memory)
                
                # 更新访问记录
                self._memory_dao.update_access(doc_id)
                
                if len(memories) >= n_results:
                    break
        
        return memories
    
    def get_memory_context(
        self,
        query: str,
        max_tokens: int = 500
    ) -> str:
        """
        获取记忆上下文 (用于构建 prompt)
        
        Args:
            query: 查询文本
            max_tokens: 最大 token 数 (粗略估算)
            
        Returns:
            格式化的记忆上下文字符串
        """
        memories = self.search_relevant_memories(
            query=query,
            n_results=10,
            min_importance=0.3
        )
        
        if not memories:
            return ""
        
        # 按重要程度排序
        memories.sort(key=lambda x: x.get("importance", 0), reverse=True)
        
        # 构建上下文
        context_parts = []
        estimated_tokens = 0
        
        for mem in memories:
            content = mem.get("content", "")
            mem_type = mem.get("type", "unknown")
            
            # 粗略估算 token (中文约 2 字符/token)
            content_tokens = len(content) // 2
            
            if estimated_tokens + content_tokens > max_tokens:
                break
            
            type_label = {
                "fact": "事实",
                "event": "事件", 
                "preference": "偏好",
                "emotion": "情感",
                "summary": "摘要"
            }.get(mem_type, mem_type)
            
            context_parts.append(f"[{type_label}] {content}")
            estimated_tokens += content_tokens
        
        return "\n".join(context_parts)
    
    def get_recent_memories(self, limit: int = 10) -> List[Dict]:
        """获取最近的记忆"""
        return self._memory_dao.get_recent_memories(
            user_id=self.user_id,
            limit=limit
        )
    
    def get_important_memories(
        self, 
        min_importance: float = 0.7,
        limit: int = 10
    ) -> List[Dict]:
        """获取重要记忆"""
        return self._memory_dao.get_important_memories(
            user_id=self.user_id,
            min_importance=min_importance,
            limit=limit
        )
    
    def update_importance(self, memory_id: str, importance: float) -> bool:
        """更新记忆重要程度"""
        success = self._memory_dao.update_importance(memory_id, importance)
        
        if success:
            # 同步更新 Chroma 的元数据
            self._vector_store.update(
                doc_id=memory_id,
                metadata={"importance": importance}
            )
        
        return success
    
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        # 从 MongoDB 删除
        success = self._memory_dao.delete_memory(memory_id)
        
        if success:
            # 从 Chroma 删除
            self._vector_store.delete([memory_id])
        
        return success
    
    def cleanup_old_memories(self, days: int = 30, max_importance: float = 0.3) -> int:
        """
        清理旧的低重要性记忆
        
        Args:
            days: 天数阈值
            max_importance: 最大重要程度
            
        Returns:
            删除数量
        """
        # 这里只删除 MongoDB 中的数据
        # Chroma 的数据可能会残留，但不影响使用
        return self._memory_dao.delete_old_memories(
            user_id=self.user_id,
            days=days,
            max_importance=max_importance
        )
