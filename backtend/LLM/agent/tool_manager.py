"""
工具管理器
管理和注册工具
"""
from typing import Dict, List, Optional, Any
import json
import logging
import traceback

from ..tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("tools")


class ToolManager:
    """
    工具管理器
    
    职责:
    1. 注册和管理工具
    2. 生成工具描述供 LLM 使用
    3. 执行工具调用
    """
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
        logger.info(f"注册工具: {tool.name}")
    
    def unregister(self, tool_name: str) -> bool:
        """注销工具"""
        if tool_name in self._tools:
            del self._tools[tool_name]
            return True
        return False
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """列出所有工具"""
        return list(self._tools.keys())
    
    def get_tools_schema(self) -> List[Dict]:
        """
        获取所有工具的 OpenAI Function Calling 格式 schema
        
        Returns:
            tools schema 列表
        """
        return [tool.to_function_schema() for tool in self._tools.values()]
    
    def get_tools_description(self) -> str:
        """
        获取工具描述文本（用于 system prompt）
        
        Returns:
            工具描述字符串
        """
        if not self._tools:
            return ""
        
        lines = ["可用工具："]
        for name, tool in self._tools.items():
            lines.append(f"\n### {name}")
            lines.append(f"描述: {tool.description}")
            if tool.parameters:
                lines.append("参数:")
                for param in tool.parameters:
                    req = "必填" if param.required else "可选"
                    lines.append(f"  - {param.name} ({param.type}, {req}): {param.description}")
        
        return "\n".join(lines)
    
    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            **kwargs: 工具参数
            
        Returns:
            ToolResult
        """
        tool = self._tools.get(tool_name)
        if not tool:
            logger.error(f"❌ 工具不存在: {tool_name}")
            return ToolResult(
                success=False, 
                error=f"工具不存在: {tool_name}"
            )
        
        try:
            logger.info(f"🔧 调用工具: {tool_name}")
            logger.info(f"   参数: {json.dumps(kwargs, ensure_ascii=False, default=str)}")
            result = tool.execute(**kwargs)
            if result.success:
                logger.info(f"   ✅ 成功: {str(result.data)[:100]}")
            else:
                logger.warning(f"   ⚠️ 失败: {result.error}")
            return result
        except Exception as e:
            logger.error(f"   ❌ 异常: {e}")
            logger.error(f"   堆栈: {traceback.format_exc()}")
            return ToolResult(success=False, error=str(e))
    
    def execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """
        批量执行工具调用（处理 LLM 返回的 tool_calls）
        
        Args:
            tool_calls: LLM 返回的工具调用列表
            
        Returns:
            工具执行结果列表（用于发回给 LLM）
        """
        results = []
        
        for call in tool_calls:
            tool_call_id = call.get("id", "")
            function = call.get("function", {})
            name = function.get("name", "")
            
            # 解析参数
            try:
                arguments = json.loads(function.get("arguments", "{}"))
            except json.JSONDecodeError:
                arguments = {}
            
            # 执行工具
            result = self.execute(name, **arguments)
            
            results.append({
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": result.to_string()
            })
        
        return results
