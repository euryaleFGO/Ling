"""
对话数据访问对象 (DAO)
负责对话记录的 CRUD 操作
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pymongo.collection import Collection
from bson import ObjectId
import uuid

from .mongo_client import get_db


class ConversationDAO:
    """对话数据访问对象"""
    
    COLLECTION_NAME = "conversations"
    
    def __init__(self):
        self._collection: Optional[Collection] = None
    
    @property
    def collection(self) -> Collection:
        if self._collection is None:
            self._collection = get_db()[self.COLLECTION_NAME]
            # 创建索引
            self._collection.create_index("session_id", unique=True)
            self._collection.create_index("user_id")
            self._collection.create_index("status")
            self._collection.create_index("created_at")
        return self._collection
    
    def create_session(
        self, 
        user_id: str = "default_user",
        metadata: Optional[Dict] = None
    ) -> str:
        """
        创建新的对话会话
        
        Args:
            user_id: 用户ID
            metadata: 额外元数据
            
        Returns:
            session_id: 会话ID
        """
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        
        doc = {
            "session_id": session_id,
            "user_id": user_id,
            "status": "active",  # active | closed
            "messages": [],
            "summary": None,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now
        }
        
        self.collection.insert_one(doc)
        return session_id
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        emotion: Optional[str] = None,
        extra: Optional[Dict] = None
    ) -> bool:
        """
        添加消息到会话
        
        Args:
            session_id: 会话ID
            role: 角色 (user | assistant | system)
            content: 消息内容
            emotion: 情感标签 (可选)
            extra: 额外信息 (可选)
            
        Returns:
            是否成功
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow(),
        }
        
        if emotion:
            message["emotion"] = emotion
        if extra:
            message["extra"] = extra
        
        result = self.collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"messages": message},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        return result.modified_count > 0
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话详情"""
        return self.collection.find_one({"session_id": session_id})
    
    def get_messages(
        self, 
        session_id: str, 
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        获取会话消息列表
        
        Args:
            session_id: 会话ID
            limit: 限制返回数量 (从最新的开始)
            
        Returns:
            消息列表
        """
        session = self.get_session(session_id)
        if not session:
            return []
        
        messages = session.get("messages", [])
        
        if limit and len(messages) > limit:
            return messages[-limit:]
        
        return messages
    
    def get_active_session(self, user_id: str = "default_user") -> Optional[Dict]:
        """获取用户当前活跃的会话"""
        return self.collection.find_one({
            "user_id": user_id,
            "status": "active"
        }, sort=[("created_at", -1)])
    
    def close_session(
        self, 
        session_id: str, 
        summary: Optional[str] = None
    ) -> bool:
        """
        关闭会话
        
        Args:
            session_id: 会话ID
            summary: 会话摘要 (可选)
            
        Returns:
            是否成功
        """
        update_data = {
            "status": "closed",
            "updated_at": datetime.utcnow()
        }
        
        if summary:
            update_data["summary"] = summary
        
        result = self.collection.update_one(
            {"session_id": session_id},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
    def get_user_sessions(
        self, 
        user_id: str = "default_user",
        status: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """获取用户的会话列表"""
        query = {"user_id": user_id}
        if status:
            query["status"] = status
        
        return list(
            self.collection.find(query)
            .sort("created_at", -1)
            .limit(limit)
        )
    
    def get_message_count(self, session_id: str) -> int:
        """获取会话消息数量"""
        session = self.get_session(session_id)
        if not session:
            return 0
        return len(session.get("messages", []))
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        result = self.collection.delete_one({"session_id": session_id})
        return result.deleted_count > 0


# 全局实例
_conversation_dao: Optional[ConversationDAO] = None


def get_conversation_dao() -> ConversationDAO:
    """获取对话DAO实例"""
    global _conversation_dao
    if _conversation_dao is None:
        _conversation_dao = ConversationDAO()
    return _conversation_dao
