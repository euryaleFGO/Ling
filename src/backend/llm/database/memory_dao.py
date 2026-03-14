"""
记忆数据访问对象 (DAO)
负责长期记忆的 CRUD 操作
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pymongo.collection import Collection
import uuid

from .mongo_client import get_db


class MemoryDAO:
    """长期记忆数据访问对象"""
    
    COLLECTION_NAME = "long_term_memory"
    
    # 记忆类型
    TYPE_FACT = "fact"           # 事实: "用户喜欢吃火锅"
    TYPE_EVENT = "event"         # 事件: "用户今天面试了"
    TYPE_PREFERENCE = "preference"  # 偏好: "用户喜欢被叫主人"
    TYPE_EMOTION = "emotion"     # 情感: "用户今天很开心"
    TYPE_SUMMARY = "summary"     # 摘要: 对话摘要
    
    def __init__(self):
        self._collection: Optional[Collection] = None
    
    @property
    def collection(self) -> Collection:
        if self._collection is None:
            self._collection = get_db()[self.COLLECTION_NAME]
            # 创建索引
            self._collection.create_index("user_id")
            self._collection.create_index("type")
            self._collection.create_index("importance")
            self._collection.create_index("created_at")
            self._collection.create_index([("content", "text")])  # 文本索引
        return self._collection
    
    def add_memory(
        self,
        content: str,
        memory_type: str,
        user_id: str = "default_user",
        importance: float = 0.5,
        source_session_id: Optional[str] = None,
        source_message_index: Optional[int] = None,
        tags: Optional[List[str]] = None,
        extra: Optional[Dict] = None
    ) -> str:
        """
        添加长期记忆
        
        Args:
            content: 记忆内容
            memory_type: 记忆类型 (fact | event | preference | emotion | summary)
            user_id: 用户ID
            importance: 重要程度 (0-1)
            source_session_id: 来源会话ID
            source_message_index: 来源消息索引
            tags: 标签列表
            extra: 额外信息
            
        Returns:
            memory_id: 记忆ID
        """
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        
        doc = {
            "memory_id": memory_id,
            "user_id": user_id,
            "type": memory_type,
            "content": content,
            "importance": importance,
            "source": {
                "session_id": source_session_id,
                "message_index": source_message_index
            } if source_session_id else None,
            "tags": tags or [],
            "extra": extra or {},
            "access_count": 0,
            "last_accessed": None,
            "created_at": now,
            "updated_at": now
        }
        
        self.collection.insert_one(doc)
        return memory_id
    
    def get_memory(self, memory_id: str) -> Optional[Dict]:
        """获取记忆详情"""
        return self.collection.find_one({"memory_id": memory_id})
    
    def get_memories_by_type(
        self,
        memory_type: str,
        user_id: str = "default_user",
        limit: int = 10
    ) -> List[Dict]:
        """按类型获取记忆"""
        return list(
            self.collection.find({
                "user_id": user_id,
                "type": memory_type
            })
            .sort("importance", -1)
            .limit(limit)
        )
    
    def get_recent_memories(
        self,
        user_id: str = "default_user",
        limit: int = 20,
        memory_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """获取最近的记忆"""
        query = {"user_id": user_id}
        if memory_types:
            query["type"] = {"$in": memory_types}
        
        return list(
            self.collection.find(query)
            .sort("created_at", -1)
            .limit(limit)
        )
    
    def get_important_memories(
        self,
        user_id: str = "default_user",
        min_importance: float = 0.7,
        limit: int = 10
    ) -> List[Dict]:
        """获取重要记忆"""
        return list(
            self.collection.find({
                "user_id": user_id,
                "importance": {"$gte": min_importance}
            })
            .sort("importance", -1)
            .limit(limit)
        )
    
    def search_memories(
        self,
        query: str,
        user_id: str = "default_user",
        limit: int = 10
    ) -> List[Dict]:
        """
        文本搜索记忆
        
        Args:
            query: 搜索关键词
            user_id: 用户ID
            limit: 返回数量
            
        Returns:
            匹配的记忆列表
        """
        return list(
            self.collection.find({
                "user_id": user_id,
                "$text": {"$search": query}
            })
            .limit(limit)
        )
    
    def update_access(self, memory_id: str) -> bool:
        """更新记忆访问记录"""
        result = self.collection.update_one(
            {"memory_id": memory_id},
            {
                "$inc": {"access_count": 1},
                "$set": {"last_accessed": datetime.utcnow()}
            }
        )
        return result.modified_count > 0
    
    def update_importance(self, memory_id: str, importance: float) -> bool:
        """更新记忆重要程度"""
        result = self.collection.update_one(
            {"memory_id": memory_id},
            {
                "$set": {
                    "importance": importance,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        result = self.collection.delete_one({"memory_id": memory_id})
        return result.deleted_count > 0
    
    def delete_old_memories(
        self,
        user_id: str = "default_user",
        days: int = 30,
        max_importance: float = 0.3
    ) -> int:
        """
        删除旧的低重要性记忆
        
        Args:
            user_id: 用户ID
            days: 天数阈值
            max_importance: 最大重要程度 (低于此值才删除)
            
        Returns:
            删除数量
        """
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        result = self.collection.delete_many({
            "user_id": user_id,
            "created_at": {"$lt": cutoff_date},
            "importance": {"$lte": max_importance}
        })
        
        return result.deleted_count


# 全局实例
_memory_dao: Optional[MemoryDAO] = None


def get_memory_dao() -> MemoryDAO:
    """获取记忆DAO实例"""
    global _memory_dao
    if _memory_dao is None:
        _memory_dao = MemoryDAO()
    return _memory_dao
