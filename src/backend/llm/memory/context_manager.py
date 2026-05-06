"""
上下文管理器
管理短期记忆（当前会话）和构建 LLM Prompt
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import math

from ..database.conversation_dao import get_conversation_dao, ConversationDAO
from ..database.knowledge_dao import get_knowledge_dao, KnowledgeDAO
from ..database.memory_dao import get_memory_dao, MemoryDAO

logger = logging.getLogger(__name__)

# Token 预算配置
MAX_HISTORY_TOKENS = 40000      # 历史消息 token 预算（约 6~8 万字）
SUMMARY_TRIGGER_TOKENS = 35000  # 触发滚动摘要的阈值
KEEP_RECENT_MESSAGES = 10       # 保留最近 N 条消息不压缩
SUMMARY_TARGET_CHARS = 500      # 摘要目标长度


def estimate_tokens(text: str) -> int:
    """粗略估算文本的 token 数（中文约 1.5 字/token）"""
    return max(1, math.ceil(len(text) / 1.5))


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
    
    def start_session(
        self,
        metadata: Optional[Dict] = None,
        previous_summary: Optional[str] = None
    ) -> str:
        """
        开始新会话

        Args:
            metadata: 额外元数据
            previous_summary: 上一会话的摘要（用于上下文继承）

        Returns:
            session_id
        """
        # 检查是否有活跃会话
        active = self._conversation_dao.get_active_session(self.user_id)
        if active:
            self._current_session_id = active["session_id"]
            logger.info(f"恢复已有会话: {self._current_session_id}")
        else:
            # 将 previous_summary 写入 metadata
            session_metadata = metadata or {}
            if previous_summary:
                session_metadata["previous_summary"] = previous_summary

            self._current_session_id = self._conversation_dao.create_session(
                user_id=self.user_id,
                metadata=session_metadata
            )
            logger.info(f"创建新会话: {self._current_session_id}")

        # 清除缓存的系统提示词（新会话需要重新构建）
        self.clear_cache()

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

        # 4. 读取上一会话摘要（从 session metadata）
        if self._current_session_id:
            session = self._conversation_dao.get_session(self._current_session_id)
            if session:
                prev_summary = session.get("metadata", {}).get("previous_summary")
                if prev_summary:
                    parts.append(f"\n上次对话摘要:\n{prev_summary}")

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
    
    def switch_user(self, new_user_id: str) -> bool:
        """
        切换用户上下文
        
        Args:
            new_user_id: 新用户 ID
            
        Returns:
            是否成功
        """
        if new_user_id == self.user_id:
            return True
        
        # 保存当前用户的会话状态
        if self._current_session_id:
            self.end_session(summary="用户切换")
        
        # 切换用户
        old_user_id = self.user_id
        self.user_id = new_user_id
        
        # 清除缓存的系统提示词
        self.clear_cache()
        
        # 启动新用户的会话
        self.start_session(metadata={"switched_from": old_user_id})
        
        logger.info(f"[上下文] 用户切换: {old_user_id} → {new_user_id}")
        return True
    
    def add_user_message_with_speaker(
        self,
        content: str,
        speaker_id: str
    ) -> bool:
        """
        添加带说话人标记的用户消息
        
        Args:
            content: 消息内容
            speaker_id: 说话人 ID
            
        Returns:
            是否成功
        """
        if not self._current_session_id:
            self.start_session()
        
        return self._conversation_dao.add_message(
            self._current_session_id,
            role="user",
            content=content,
            metadata={"speaker_id": speaker_id}
        )
    
    def get_history_by_speaker(
        self,
        speaker_id: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        获取特定说话人的对话历史
        
        Args:
            speaker_id: 说话人 ID
            limit: 限制数量
            
        Returns:
            消息列表
        """
        if not self._current_session_id:
            return []
        
        all_messages = self._conversation_dao.get_messages(
            self._current_session_id,
            limit=None
        )
        
        # 过滤出指定说话人的消息
        filtered = [
            msg for msg in all_messages
            if msg.get("metadata", {}).get("speaker_id") == speaker_id
        ]
        
        if limit:
            filtered = filtered[-limit:]
        
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in filtered
        ]

    def set_llm_client(self, llm_client):
        """注入 LLM 客户端用于滚动摘要生成"""
        self._llm = llm_client

    def build_messages_with_summary(
        self,
        user_input: str,
        include_history: bool = True,
        retrieved_context: Optional[str] = None
    ) -> List[Dict]:
        """
        构建消息列表，支持滚动摘要

        当历史消息 token 超过阈值时，自动将早期消息压缩为摘要。
        """
        messages = []

        # 1. System prompt
        system_content = self.get_system_prompt()

        if retrieved_context:
            system_content += f"\n\n参考信息:\n{retrieved_context}"

        messages.append({"role": "system", "content": system_content})

        if not include_history:
            messages.append({"role": "user", "content": user_input})
            return messages

        # 2. 获取全部历史
        history = self._conversation_dao.get_messages(
            self._current_session_id,
            limit=None  # 获取全部，自己控制 token
        )

        if not history:
            messages.append({"role": "user", "content": user_input})
            return messages

        # 3. 计算总 token
        total_tokens = sum(estimate_tokens(m.get("content", "")) for m in history)

        if total_tokens <= SUMMARY_TRIGGER_TOKENS:
            # 未超限，直接用全部历史
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        else:
            # 超过阈值，启用滚动摘要
            if len(history) > KEEP_RECENT_MESSAGES:
                early_messages = history[:-KEEP_RECENT_MESSAGES]
                recent_messages = history[-KEEP_RECENT_MESSAGES:]

                # 生成摘要
                summary = self._generate_rolling_summary(early_messages)
                if summary:
                    messages.append({
                        "role": "system",
                        "content": f"[之前的对话摘要]\n{summary}"
                    })

                # 添加最近消息
                for msg in recent_messages:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            else:
                for msg in history:
                    messages.append({"role": msg["role"], "content": msg["content"]})

        # 4. 当前用户输入
        messages.append({"role": "user", "content": user_input})
        return messages

    def _generate_rolling_summary(self, messages: List[Dict]) -> str:
        """
        用 LLM 将早期消息压缩为摘要
        """
        if not messages:
            return ""

        # 构建对话文本
        conversation_text = ""
        for msg in messages:
            role = "用户" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "")
            conversation_text += f"{role}: {content}\n"

        # 限制输入长度
        if len(conversation_text) > 8000:
            conversation_text = conversation_text[:8000] + "\n...(对话过长，已截断)"

        prompt = f"""请将以下对话压缩为一段简洁的摘要（约{SUMMARY_TARGET_CHARS}字），保留关键信息、用户偏好、重要决定和未完成的话题。用第三人称描述。

对话内容：
{conversation_text}

摘要："""

        try:
            if hasattr(self, '_llm') and self._llm:
                response = self._llm.infer(
                    messages=[{"role": "user", "content": prompt}],
                    stream=False,
                    temperature=0.3
                )
                summary = response.choices[0].message.content
                logger.info(f"[滚动摘要] 生成摘要: {summary[:80]}...")
                return summary
            else:
                logger.warning("[滚动摘要] 无 LLM 客户端，使用回退方案")
                return self._fallback_summary(messages)
        except Exception as e:
            logger.error(f"[滚动摘要] 生成失败: {e}")
            return self._fallback_summary(messages)

    def _fallback_summary(self, messages: List[Dict]) -> str:
        """无 LLM 时的回退摘要"""
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        if user_msgs:
            return f"之前讨论了: {', '.join(user_msgs[:5])}..."
        return "之前的对话记录。"
