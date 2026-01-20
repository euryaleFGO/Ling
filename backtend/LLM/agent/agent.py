"""
Agent 核心
支持工具调用的智能代理
"""
from typing import Optional, List, Dict, Generator, Any
import logging
import json

from ..api_infer.openai_infer import APIInfer
from ..api_infer.config import DEEPSEEK_API_KEY, BASE_URL, MODEL
from ..memory.context_manager import ContextManager
from ..memory.long_term_memory import LongTermMemoryManager
from ..database.knowledge_dao import get_knowledge_dao
from .tool_manager import ToolManager
from ..tools import DateTimeTool, MemoryTool, SearchTool, SummaryTool
from ..utils.logging_config import setup_logging, get_logger, log_llm_request, log_llm_response, log_error

# 初始化日志
setup_logging(level=logging.DEBUG, log_file=True, console=False)
logger = get_logger("agent")


class Agent:
    """
    智能代理
    
    特性:
    1. 自主决定是否调用工具
    2. 支持多轮工具调用
    3. 自动总结对话并提取记忆
    """
    
    MAX_TOOL_CALLS = 5  # 单次对话最大工具调用次数
    
    def __init__(
        self,
        user_id: str = "default_user",
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        enable_tools: bool = True
    ):
        self.user_id = user_id
        self.enable_tools = enable_tools
        
        # LLM 客户端
        self._llm = APIInfer(
            url=base_url or BASE_URL,
            api_key=api_key or DEEPSEEK_API_KEY,
            model_name=model or MODEL
        )
        
        # 记忆管理
        self._context_manager = ContextManager(user_id=user_id)
        self._memory_manager = LongTermMemoryManager(user_id=user_id)
        self._knowledge_dao = get_knowledge_dao()
        
        # 工具管理
        self._tool_manager = ToolManager()
        self._setup_tools()
    
    def _setup_tools(self):
        """初始化工具"""
        if not self.enable_tools:
            return
        
        # 注册日期时间工具
        self._tool_manager.register(DateTimeTool())
        
        # 注册记忆工具
        memory_tool = MemoryTool()
        memory_tool.set_memory_manager(self._memory_manager)
        self._tool_manager.register(memory_tool)
        
        # 注册搜索工具
        self._tool_manager.register(SearchTool())
        
        # 注册截图工具
        from ..tools import ScreenshotTool
        self._tool_manager.register(ScreenshotTool())
        
        # 注册文件操作工具
        from ..tools import FileWriteTool, FileReadTool
        self._tool_manager.register(FileWriteTool())
        self._tool_manager.register(FileReadTool())
        
        # 注册总结工具（内部使用）
        summary_tool = SummaryTool()
        summary_tool.set_llm_client(self._llm)
        self._summary_tool = summary_tool
    
    def start_chat(self) -> str:
        """开始聊天会话"""
        session_id = self._context_manager.start_session()
        logger.info(f"Agent 会话开始: {session_id}")
        return session_id
    
    def end_chat(self, auto_summarize: bool = True) -> bool:
        """
        结束聊天会话
        
        Args:
            auto_summarize: 是否自动总结并提取记忆
        """
        if auto_summarize:
            self._auto_extract_memories()
        
        success = self._context_manager.end_session()
        if success:
            logger.info("Agent 会话结束")
        return success
    
    def _auto_extract_memories(self):
        """自动提取记忆"""
        history = self._context_manager.get_history()
        if not history or len(history) < 2:
            return
        
        try:
            result = self._summary_tool.execute(
                messages=history,
                extract_memories=True
            )
            
            if result.success and result.data:
                memories = result.data.get("memories", [])
                for mem in memories:
                    if mem.get("content") and mem.get("importance", 0) >= 0.5:
                        self._memory_manager.add_memory(
                            content=mem["content"],
                            memory_type=mem.get("type", "fact"),
                            importance=mem.get("importance", 0.5),
                            source_session_id=self._context_manager.session_id
                        )
                        logger.info(f"自动保存记忆: {mem['content'][:30]}...")
        except Exception as e:
            logger.error(f"自动提取记忆失败: {e}")
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        parts = []
        
        # 1. 角色设定
        character = self._knowledge_dao.get_active_character()
        if character:
            parts.append(character.get("system_prompt", ""))
        
        # 2. 当前时间（即使有工具，也提供基本时间）
        from datetime import datetime
        now = datetime.now()
        weekdays = ['一', '二', '三', '四', '五', '六', '日']
        parts.append(f"\n当前时间: {now.strftime('%Y年%m月%d日 %H:%M')} 星期{weekdays[now.weekday()]}")
        
        # 3. 用户信息
        user_profile = self._knowledge_dao.get_user_profile(self.user_id)
        if user_profile:
            nickname = user_profile.get("nickname", "用户")
            parts.append(f"\n用户称呼: {nickname}")
        
        # 4. 重要记忆
        important_memories = self._memory_manager.get_important_memories(
            min_importance=0.7,
            limit=5
        )
        if important_memories:
            memory_texts = [m["content"] for m in important_memories]
            parts.append(f"\n关于用户的重要信息:\n" + "\n".join(f"- {t}" for t in memory_texts))
        
        # 5. 工具使用说明（如果启用）
        if self.enable_tools and self._tool_manager.list_tools():
            parts.append(f"""
工具使用说明：
你可以调用工具来获取信息或执行操作。当用户询问实时信息（如日期时间）时，优先使用工具获取准确数据。
当用户分享重要的个人信息时，使用记忆工具保存。
不要滥用工具，简单的闲聊不需要工具。""")
        
        return "\n".join(parts)
    
    def chat(
        self,
        message: str,
        stream: bool = True
    ) -> Generator[str, None, None]:
        """
        发送消息并获取回复（流式）
        
        支持工具调用的完整流程
        """
        # 确保有活跃会话
        if not self._context_manager.session_id:
            self.start_chat()
        
        # 添加用户消息
        self._context_manager.add_user_message(message)
        
        # 构建消息
        messages = self._build_messages(message)
        
        # 获取工具 schema
        tools = self._tool_manager.get_tools_schema() if self.enable_tools else None
        
        # 调用 LLM
        full_response = []
        tool_call_count = 0
        
        logger.info(f"👤 用户消息: {message[:50]}{'...' if len(message) > 50 else ''}")
        
        while tool_call_count < self.MAX_TOOL_CALLS:
            log_llm_request(len(messages), tools is not None)
            
            response = self._llm.infer(
                messages=messages,
                stream=False,  # 工具调用模式下先不流式
                tools=tools if self.enable_tools else None
            )
            
            choice = response.choices[0]
            assistant_message = choice.message
            
            # 检查是否有工具调用
            if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                tool_call_count += 1
                log_llm_response(True)
                
                # 添加助手消息（包含工具调用）
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ]
                })
                
                # 执行工具调用
                tool_calls_data = [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in assistant_message.tool_calls
                ]
                tool_results = self._tool_manager.execute_tool_calls(tool_calls_data)
                
                # 添加工具结果
                messages.extend(tool_results)
                
                # 继续循环，让 LLM 处理工具结果
                continue
            
            # 没有工具调用，返回最终回复
            content = assistant_message.content or ""
            full_response.append(content)
            
            if stream:
                # 模拟流式输出
                for char in content:
                    yield char
            else:
                yield content
            
            break
        
        # 保存助手回复
        final_response = "".join(full_response)
        self._context_manager.add_assistant_message(final_response)
    
    def _build_messages(self, user_input: str) -> List[Dict]:
        """构建发送给 LLM 的消息"""
        messages = []
        
        # System prompt
        messages.append({
            "role": "system",
            "content": self._build_system_prompt()
        })
        
        # 对话历史
        history = self._context_manager.get_history()
        messages.extend(history)
        
        # 当前用户输入
        messages.append({
            "role": "user",
            "content": user_input
        })
        
        return messages
    
    def chat_sync(self, message: str) -> str:
        """同步聊天（非流式）"""
        response_parts = list(self.chat(message, stream=False))
        return "".join(response_parts)
    
    def get_greeting(self) -> str:
        """获取打招呼语"""
        character = self._knowledge_dao.get_active_character()
        if character:
            return character.get("greeting", "你好~")
        return "你好~"
    
    def get_memories(self, limit: int = 10) -> List[Dict]:
        """获取用户记忆"""
        return self._memory_manager.get_recent_memories(limit=limit)
    
    def get_session_info(self) -> Dict:
        """获取会话信息"""
        return self._context_manager.get_session_info()
