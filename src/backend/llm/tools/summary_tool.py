"""
对话总结工具
使用 LLM 自动提取和总结对话中的重要信息
"""
from typing import List, Optional, Dict, Any
from .base_tool import BaseTool, ToolParameter, ToolResult


class SummaryTool(BaseTool):
    """对话总结工具 - 内部使用，由 Agent 自动调用"""
    
    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM 客户端用于生成总结
        """
        self._llm = llm_client
    
    def set_llm_client(self, llm_client):
        """设置 LLM 客户端"""
        self._llm = llm_client
    
    @property
    def name(self) -> str:
        return "summarize_conversation"
    
    @property
    def description(self) -> str:
        return """总结和提取对话中的重要信息。
这是一个内部工具，通常在对话结束时自动调用。
用于：
1. 提取用户分享的重要个人信息
2. 总结对话主题
3. 识别需要记住的事项"""
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="messages",
                type="array",
                description="对话消息列表",
                required=True
            ),
            ToolParameter(
                name="extract_memories",
                type="boolean",
                description="是否提取记忆点",
                required=False,
                default=True
            )
        ]
    
    def execute(
        self, 
        messages: List[Dict[str, str]],
        extract_memories: bool = True,
        **kwargs
    ) -> ToolResult:
        """
        总结对话
        
        Args:
            messages: 对话消息列表 [{"role": "user", "content": "..."}, ...]
            extract_memories: 是否提取记忆
        """
        if not messages:
            return ToolResult(success=True, data={"summary": "", "memories": []})
        
        if not self._llm:
            # 如果没有 LLM，使用简单的规则提取
            return self._simple_extract(messages)
        
        try:
            # 使用 LLM 进行智能总结
            return self._llm_extract(messages, extract_memories)
        except Exception as e:
            # 降级到简单提取
            return self._simple_extract(messages)
    
    def _llm_extract(
        self, 
        messages: List[Dict[str, str]], 
        extract_memories: bool
    ) -> ToolResult:
        """使用 LLM 提取"""
        # 构建对话文本
        conversation = "\n".join([
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
            for m in messages
        ])
        
        prompt = f"""请分析以下对话，提取重要信息。

对话内容：
{conversation}

请以JSON格式返回：
{{
    "summary": "对话主题的简短总结（一句话）",
    "memories": [
        {{
            "content": "需要记住的具体信息",
            "type": "fact/preference/event/emotion",
            "importance": 0.1-1.0的重要程度
        }}
    ],
    "topics": ["讨论的主题列表"]
}}

注意：
1. 只提取用户明确表达的信息，不要推测
2. 重要程度：姓名/身份=0.9，喜好=0.7，日常事件=0.5，闲聊=不记录
3. 如果没有值得记录的信息，memories返回空数组
4. 只返回JSON，不要其他内容"""

        response = self._llm.infer(
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        
        content = response.choices[0].message.content
        
        # 解析 JSON
        import json
        import re
        
        # 尝试提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            data = json.loads(json_match.group())
            return ToolResult(success=True, data=data)
        
        return ToolResult(success=False, error="无法解析LLM返回的JSON")
    
    def _simple_extract(self, messages: List[Dict[str, str]]) -> ToolResult:
        """简单规则提取（降级方案）"""
        user_messages = [m["content"] for m in messages if m["role"] == "user"]
        
        # 简单统计主题
        topics = []
        if any("游戏" in m for m in user_messages):
            topics.append("游戏")
        if any("工作" in m for m in user_messages):
            topics.append("工作")
        if any("学习" in m for m in user_messages):
            topics.append("学习")
        
        return ToolResult(
            success=True,
            data={
                "summary": f"共进行了{len(messages)}轮对话",
                "memories": [],
                "topics": topics or ["日常聊天"]
            }
        )
