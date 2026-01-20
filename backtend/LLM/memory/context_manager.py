"""
上下文管理器
管理短期记忆（当前会话）和构建 LLM Prompt
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from ..database.conversation_dao import get_conversation_dao, ConversationDAO
from ..database.knowledge_dao import get_knowledge_dao, KnowledgeDAO
from ..database.memory_dao import get_memory_dao, MemoryDAO

logger = logging.getLogger(__name__)


class ContextManager:
    """
    上下文管理器
    
    职责:
    1. 管理当前会话 (短期记忆)
    2. 构建发送给 LLM 的 messages
    3. 控制上下文长度
    """
    
    def __init__(
        self,
        user_id: str = "default_user",
        max_history_messages: int = 20,  # 最大历史消息数
        max_context_tokens: int = 4000,  # 最大上下文 token 数 (预估)
    ):
        self.user_id = user_id
        self.max_history_messages = max_history_messages
        self.max_context_tokens = max_context_tokens
        
        self._conversation_dao: ConversationDAO = get_conversation_dao()
        self._knowledge_dao: KnowledgeDAO = get_knowledge_dao()
        self._memory_dao: MemoryDAO = get_memory_dao()
        
        self._current_session_id: Optional[str] = None
        self._system_prompt: Optional[str] = None
    
    @property
    def session_id(self) -> Optional[str]:
        """当前会话ID"""
        return self._current_session_id
    
    def start_session(self, metadata: Optional[Dict] = None) -> str:
        """
        开始新会话
        
        Returns:
            session_id
        """
        # 检查是否有活跃会话
        active = self._conversation_dao.get_active_session(self.user_id)
        if active:
            self._current_session_id = active["session_id"]
            logger.info(f"恢复已有会话: {self._current_session_id}")
        else:
            self._current_session_id = self._conversation_dao.create_session(
                user_id=self.user_id,
                metadata=metadata
            )
            logger.info(f"创建新会话: {self._current_session_id}")
        
        return self._current_session_id
    
    def end_session(self, summary: Optional[str] = None) -> bool:
        """
        结束当前会话
        
        Args:
            summary: 会话摘要
            
        Returns:
            是否成功
        """
        if not self._current_session_id:
            return False
        
        success = self._conversation_dao.close_session(
            self._current_session_id, 
            summary
        )
        
        if success:
            logger.info(f"会话已关闭: {self._current_session_id}")
            self._current_session_id = None
        
        return success
    
    def add_user_message(self, content: str) -> bool:
        """添加用户消息"""
        if not self._current_session_id:
            self.start_session()
        
        return self._conversation_dao.add_message(
            self._current_session_id,
            role="user",
            content=content
        )
    
    def add_assistant_message(
        self, 
        content: str, 
        emotion: Optional[str] = None
    ) -> bool:
        """添加助手消息"""
        if not self._current_session_id:
            return False
        
        return self._conversation_dao.add_message(
            self._current_session_id,
            role="assistant",
            content=content,
            emotion=emotion
        )
    
    def get_history(self, limit: Optional[int] = None) -> List[Dict]:
        """
        获取对话历史
        
        Args:
            limit: 限制数量
            
        Returns:
            消息列表 [{"role": "user", "content": "..."}, ...]
        """
        if not self._current_session_id:
            return []
        
        messages = self._conversation_dao.get_messages(
            self._current_session_id,
            limit=limit or self.max_history_messages
        )
        
        # 转换为 OpenAI 格式
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
        ]
    
    def get_system_prompt(self) -> str:
        """
        获取系统提示词
        
        包含:
        1. 角色人设
        2. 用户偏好
        3. 重要长期记忆
        4. 当前日期时间
        """
        if self._system_prompt:
            return self._system_prompt
        
        parts = []
        
        # 1. 获取角色设定
        character = self._knowledge_dao.get_active_character()
        if character:
            parts.append(character.get("system_prompt", ""))
        
        # 添加当前日期时间
        now = datetime.now()
        weekdays = ['一', '二', '三', '四', '五', '六', '日']
        parts.append(f"\n当前日期时间: {now.strftime('%Y年%m月%d日 %H:%M')} (星期{weekdays[now.weekday()]})")
        
        # 2. 获取用户偏好
        user_profile = self._knowledge_dao.get_user_profile(self.user_id)
        if user_profile:
            nickname = user_profile.get("nickname", "用户")
            parts.append(f"\n用户希望你称呼他为: {nickname}")
            
            prefs = user_profile.get("preferences", {})
            if prefs.get("topics_like"):
                parts.append(f"用户喜欢的话题: {', '.join(prefs['topics_like'])}")
            if prefs.get("topics_avoid"):
                parts.append(f"用户不喜欢的话题: {', '.join(prefs['topics_avoid'])}")
        
        # 3. 获取重要长期记忆
        important_memories = self._memory_dao.get_important_memories(
            self.user_id,
            min_importance=0.7,
            limit=5
        )
        if important_memories:
            memory_texts = [m["content"] for m in important_memories]
            parts.append(f"\n关于用户的重要信息:\n" + "\n".join(f"- {t}" for t in memory_texts))
        
        self._system_prompt = "\n".join(parts)
        return self._system_prompt
    
    def build_messages(
        self, 
        user_input: str,
        include_history: bool = True,
        retrieved_context: Optional[str] = None
    ) -> List[Dict]:
        """
        构建发送给 LLM 的完整消息列表
        
        Args:
            user_input: 用户当前输入
            include_history: 是否包含历史
            retrieved_context: RAG 检索到的上下文
            
        Returns:
            messages 列表
        """
        messages = []
        
        # 1. System prompt
        system_content = self.get_system_prompt()
        
        # 添加 RAG 检索结果
        if retrieved_context:
            system_content += f"\n\n参考信息:\n{retrieved_context}"
        
        messages.append({
            "role": "system",
            "content": system_content
        })
        
        # 2. 对话历史
        if include_history:
            history = self.get_history()
            messages.extend(history)
        
        # 3. 当前用户输入
        messages.append({
            "role": "user",
            "content": user_input
        })
        
        return messages
    
    def clear_cache(self):
        """清除缓存"""
        self._system_prompt = None
    
    def get_session_info(self) -> Dict:
        """获取当前会话信息"""
        if not self._current_session_id:
            return {"status": "no_session"}
        
        session = self._conversation_dao.get_session(self._current_session_id)
        if not session:
            return {"status": "session_not_found"}
        
        return {
            "status": "active",
            "session_id": self._current_session_id,
            "message_count": len(session.get("messages", [])),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at")
        }
