"""
知识库数据访问对象 (DAO)
负责角色设定、知识库的 CRUD 操作
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pymongo.collection import Collection
import uuid

from .mongo_client import get_db


class KnowledgeDAO:
    """知识库数据访问对象"""
    
    COLLECTION_NAME = "knowledge_base"
    CHARACTER_COLLECTION = "character_settings"
    USER_PROFILE_COLLECTION = "user_profiles"
    
    # 知识类型
    TYPE_CHARACTER = "character"      # 角色设定
    TYPE_WORLD = "world"              # 世界观
    TYPE_REFERENCE = "reference"      # 参考资料
    TYPE_FAQ = "faq"                  # 常见问答
    
    def __init__(self):
        self._collection: Optional[Collection] = None
        self._character_collection: Optional[Collection] = None
        self._user_collection: Optional[Collection] = None
    
    @property
    def collection(self) -> Collection:
        if self._collection is None:
            self._collection = get_db()[self.COLLECTION_NAME]
            self._collection.create_index("type")
            self._collection.create_index("tags")
            self._collection.create_index([("content", "text")])
        return self._collection
    
    @property
    def character_collection(self) -> Collection:
        if self._character_collection is None:
            self._character_collection = get_db()[self.CHARACTER_COLLECTION]
            self._character_collection.create_index("name", unique=True)
        return self._character_collection
    
    @property
    def user_collection(self) -> Collection:
        if self._user_collection is None:
            self._user_collection = get_db()[self.USER_PROFILE_COLLECTION]
            self._user_collection.create_index("user_id", unique=True)
        return self._user_collection
    
    # ==================== 角色设定 ====================
    
    def create_character(
        self,
        name: str,
        personality: Dict[str, Any],
        background: str,
        system_prompt: str,
        greeting: str = "你好~",
        extra: Optional[Dict] = None
    ) -> str:
        """
        创建角色设定
        
        Args:
            name: 角色名称
            personality: 性格特征
                - traits: List[str] 性格特点
                - speech_style: str 说话风格
                - interests: List[str] 兴趣爱好
            background: 背景故事
            system_prompt: 系统提示词
            greeting: 打招呼语
            extra: 额外信息
            
        Returns:
            character_id
        """
        now = datetime.utcnow()
        
        doc = {
            "character_id": f"char_{uuid.uuid4().hex[:8]}",
            "name": name,
            "personality": personality,
            "background": background,
            "system_prompt": system_prompt,
            "greeting": greeting,
            "extra": extra or {},
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }
        
        # 使用 upsert 避免重复
        self.character_collection.update_one(
            {"name": name},
            {"$set": doc},
            upsert=True
        )
        
        return doc["character_id"]
    
    def get_character(self, name: str) -> Optional[Dict]:
        """获取角色设定"""
        return self.character_collection.find_one({"name": name})
    
    def get_active_character(self) -> Optional[Dict]:
        """获取当前激活的角色"""
        return self.character_collection.find_one({"is_active": True})
    
    def update_character(self, name: str, updates: Dict) -> bool:
        """更新角色设定"""
        updates["updated_at"] = datetime.utcnow()
        result = self.character_collection.update_one(
            {"name": name},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    def set_active_character(self, name: str) -> bool:
        """设置激活角色"""
        # 先把所有角色设为非激活
        self.character_collection.update_many(
            {},
            {"$set": {"is_active": False}}
        )
        # 激活指定角色
        result = self.character_collection.update_one(
            {"name": name},
            {"$set": {"is_active": True}}
        )
        return result.modified_count > 0
    
    # ==================== 用户档案 ====================
    
    def create_user_profile(
        self,
        user_id: str = "default_user",
        nickname: str = "主人",
        preferences: Optional[Dict] = None
    ) -> str:
        """
        创建用户档案
        
        Args:
            user_id: 用户ID
            nickname: 昵称 (角色怎么称呼用户)
            preferences: 偏好设置
            
        Returns:
            user_id
        """
        now = datetime.utcnow()
        
        doc = {
            "user_id": user_id,
            "nickname": nickname,
            "preferences": preferences or {
                "call_me": nickname,
                "topics_like": [],
                "topics_avoid": []
            },
            "stats": {
                "total_conversations": 0,
                "total_messages": 0,
                "first_chat": now
            },
            "created_at": now,
            "updated_at": now
        }
        
        self.user_collection.update_one(
            {"user_id": user_id},
            {"$set": doc},
            upsert=True
        )
        
        return user_id
    
    def get_user_profile(self, user_id: str = "default_user") -> Optional[Dict]:
        """获取用户档案"""
        return self.user_collection.find_one({"user_id": user_id})
    
    def update_user_profile(self, user_id: str, updates: Dict) -> bool:
        """更新用户档案"""
        updates["updated_at"] = datetime.utcnow()
        result = self.user_collection.update_one(
            {"user_id": user_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    def increment_user_stats(
        self, 
        user_id: str = "default_user",
        conversations: int = 0,
        messages: int = 0
    ) -> bool:
        """增加用户统计"""
        result = self.user_collection.update_one(
            {"user_id": user_id},
            {
                "$inc": {
                    "stats.total_conversations": conversations,
                    "stats.total_messages": messages
                },
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        return result.modified_count > 0
    
    # ==================== 知识库 ====================
    
    def add_knowledge(
        self,
        content: str,
        knowledge_type: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        extra: Optional[Dict] = None
    ) -> str:
        """
        添加知识条目
        
        Args:
            content: 知识内容
            knowledge_type: 类型 (character | world | reference | faq)
            title: 标题
            tags: 标签
            extra: 额外信息
            
        Returns:
            knowledge_id
        """
        knowledge_id = f"kb_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        
        doc = {
            "knowledge_id": knowledge_id,
            "type": knowledge_type,
            "title": title,
            "content": content,
            "tags": tags or [],
            "extra": extra or {},
            "created_at": now,
            "updated_at": now
        }
        
        self.collection.insert_one(doc)
        return knowledge_id
    
    def get_knowledge(self, knowledge_id: str) -> Optional[Dict]:
        """获取知识条目"""
        return self.collection.find_one({"knowledge_id": knowledge_id})
    
    def search_knowledge(
        self,
        query: str,
        knowledge_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """搜索知识库"""
        search_query = {"$text": {"$search": query}}
        if knowledge_type:
            search_query["type"] = knowledge_type
        
        return list(
            self.collection.find(search_query)
            .limit(limit)
        )
    
    def get_knowledge_by_type(
        self,
        knowledge_type: str,
        limit: int = 50
    ) -> List[Dict]:
        """按类型获取知识"""
        return list(
            self.collection.find({"type": knowledge_type})
            .sort("created_at", -1)
            .limit(limit)
        )
    
    def delete_knowledge(self, knowledge_id: str) -> bool:
        """删除知识条目"""
        result = self.collection.delete_one({"knowledge_id": knowledge_id})
        return result.deleted_count > 0
    
    # ==================== GUI 简化接口 ====================
    
    def get_character_settings(self) -> Optional[Dict]:
        """
        获取角色设置（GUI 用）
        返回简化的设置字典
        """
        char = self.get_active_character()
        if char:
            return {
                'name': char.get('name', ''),
                'nickname': char.get('extra', {}).get('nickname', ''),
                'user_name': char.get('extra', {}).get('user_name', ''),
                'personality': char.get('personality', {}).get('description', ''),
                'system_prompt': char.get('system_prompt', '')
            }
        return None
    
    def save_character_settings(self, settings: Dict) -> bool:
        """
        保存角色设置（GUI 用）
        
        Args:
            settings: {
                'name': 角色名,
                'nickname': 昵称,
                'user_name': 用户称呼,
                'personality': 性格描述,
                'system_prompt': 系统提示词
            }
        """
        name = settings.get('name', '玲')
        
        # 构建完整的角色数据
        personality = {
            'description': settings.get('personality', ''),
            'traits': []
        }
        
        extra = {
            'nickname': settings.get('nickname', ''),
            'user_name': settings.get('user_name', '')
        }
        
        system_prompt = settings.get('system_prompt', '')
        if not system_prompt:
            # 使用默认模板
            system_prompt = f"""你是{name}，一个可爱的AI助手。
{settings.get('personality', '')}
用户称呼你为{settings.get('nickname', name)}，你称呼用户为{settings.get('user_name', '主人')}。
请用温柔、可爱的语气与用户对话。"""
        
        self.create_character(
            name=name,
            personality=personality,
            background="",
            system_prompt=system_prompt,
            greeting=f"你好呀，{settings.get('user_name', '主人')}~",
            extra=extra
        )
        
        self.set_active_character(name)
        return True


# 全局实例
_knowledge_dao: Optional[KnowledgeDAO] = None


def get_knowledge_dao() -> KnowledgeDAO:
    """获取知识库DAO实例"""
    global _knowledge_dao
    if _knowledge_dao is None:
        _knowledge_dao = KnowledgeDAO()
    return _knowledge_dao
