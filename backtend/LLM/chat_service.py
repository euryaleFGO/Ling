"""
聊天服务
整合 LLM 推理、记忆管理、上下文构建
"""
from typing import Optional, List, Dict, Generator, Any
import logging

from .api_infer.openai_infer import APIInfer
from .api_infer.config import DEEPSEEK_API_KEY, BASE_URL, MODEL
from .memory.context_manager import ContextManager
from .memory.long_term_memory import LongTermMemoryManager
from .memory.memory_extractor import MemoryExtractor
from .database.knowledge_dao import get_knowledge_dao

logger = logging.getLogger(__name__)


class ChatService:
    """
    聊天服务
    
    整合:
    1. LLM 推理
    2. 上下文管理 (短期记忆)
    3. 长期记忆管理
    4. RAG 检索
    5. 记忆提取
    """
    
    def __init__(
        self,
        user_id: str = "default_user",
        api_key: str = None,
        base_url: str = None,
        model: str = None
    ):
        self.user_id = user_id
        
        # LLM 客户端
        self._llm = APIInfer(
            url=base_url or BASE_URL,
            api_key=api_key or DEEPSEEK_API_KEY,
            model_name=model or MODEL
        )
        
        # 记忆管理
        self._context_manager = ContextManager(user_id=user_id)
        self._memory_manager = LongTermMemoryManager(user_id=user_id)
        self._memory_extractor = MemoryExtractor()
        self._knowledge_dao = get_knowledge_dao()
    
    def start_chat(self) -> str:
        """
        开始聊天会话
        
        Returns:
            session_id
        """
        session_id = self._context_manager.start_session()
        logger.info(f"聊天会话开始: {session_id}")
        return session_id
    
    def end_chat(self, generate_summary: bool = True) -> bool:
        """
        结束聊天会话
        
        Args:
            generate_summary: 是否生成摘要
            
        Returns:
            是否成功
        """
        summary = None
        
        if generate_summary:
            # 获取对话历史
            history = self._context_manager.get_history()
            if history:
                # 提取记忆
                memories = self._memory_extractor.extract_from_conversation(history)
                for mem in memories:
                    self._memory_manager.add_memory(
                        content=mem["content"],
                        memory_type=mem["type"],
                        importance=mem["importance"],
                        source_session_id=self._context_manager.session_id
                    )
                
                # 生成简单摘要
                user_msgs = [m["content"] for m in history if m["role"] == "user"]
                if user_msgs:
                    summary = f"讨论了: {', '.join(user_msgs[:3])}..."
        
        success = self._context_manager.end_session(summary)
        if success:
            logger.info("聊天会话结束")
        return success
    
    def chat(
        self,
        message: str,
        stream: bool = True,
        use_rag: bool = True,
        extract_memory: bool = True
    ) -> Generator[str, None, None]:
        """
        发送消息并获取回复 (流式)
        
        Args:
            message: 用户消息
            stream: 是否流式返回
            use_rag: 是否使用 RAG 检索
            extract_memory: 是否提取记忆
            
        Yields:
            回复内容片段
        """
        # 1. 确保有活跃会话
        if not self._context_manager.session_id:
            self.start_chat()
        
        # 2. 添加用户消息
        self._context_manager.add_user_message(message)
        
        # 3. 即时提取记忆 (简单规则提取)
        if extract_memory:
            memories = self._memory_extractor.extract_from_message(message, "user")
            for mem in memories:
                self._memory_manager.add_memory(
                    content=mem["content"],
                    memory_type=mem["type"],
                    importance=mem["importance"],
                    source_session_id=self._context_manager.session_id
                )
        
        # 4. RAG 检索相关记忆
        retrieved_context = None
        if use_rag:
            retrieved_context = self._memory_manager.get_memory_context(
                query=message,
                max_tokens=300
            )
        
        # 5. 构建 messages
        messages = self._context_manager.build_messages(
            user_input=message,
            include_history=True,
            retrieved_context=retrieved_context
        )
        
        # 6. 调用 LLM
        response = self._llm.infer(messages=messages, stream=stream)
        
        # 7. 收集并返回回复
        full_response = []
        
        if stream:
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    full_response.append(content)
                    yield content
        else:
            content = response.choices[0].message.content
            full_response.append(content)
            yield content
        
        # 8. 保存助手回复
        assistant_message = "".join(full_response)
        self._context_manager.add_assistant_message(assistant_message)
    
    def chat_sync(
        self,
        message: str,
        use_rag: bool = True,
        extract_memory: bool = True
    ) -> str:
        """
        同步聊天 (非流式)
        
        Returns:
            完整回复
        """
        response_parts = list(self.chat(
            message=message,
            stream=False,
            use_rag=use_rag,
            extract_memory=extract_memory
        ))
        return "".join(response_parts)
    
    def get_greeting(self) -> str:
        """获取角色打招呼语"""
        character = self._knowledge_dao.get_active_character()
        if character:
            return character.get("greeting", "你好~")
        return "你好~"
    
    def get_session_info(self) -> Dict:
        """获取会话信息"""
        return self._context_manager.get_session_info()
    
    def get_memories(self, limit: int = 10) -> List[Dict]:
        """获取用户记忆"""
        return self._memory_manager.get_recent_memories(limit=limit)


def create_chat_service(user_id: str = "default_user") -> ChatService:
    """创建聊天服务实例"""
    return ChatService(user_id=user_id)
