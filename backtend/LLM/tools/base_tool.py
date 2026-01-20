"""
工具基类
定义工具的标准接口
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    
    def to_string(self) -> str:
        """转换为字符串供 LLM 阅读"""
        if self.success:
            if isinstance(self.data, dict):
                return json.dumps(self.data, ensure_ascii=False, indent=2)
            return str(self.data)
        return f"错误: {self.error}"


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str  # string, number, boolean, array, object
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    default: Any = None


class BaseTool(ABC):
    """
    工具基类
    
    所有工具都需要继承此类并实现:
    1. name: 工具名称
    2. description: 工具描述
    3. parameters: 参数定义
    4. execute(): 执行方法
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（唯一标识）"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（告诉 LLM 什么时候使用）"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> List[ToolParameter]:
        """参数列表"""
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        执行工具
        
        Args:
            **kwargs: 参数
            
        Returns:
            ToolResult
        """
        pass
    
    def to_function_schema(self) -> Dict:
        """
        转换为 OpenAI Function Calling 格式
        
        Returns:
            函数定义 schema
        """
        properties = {}
        required = []
        
        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            }
        }
    
    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"
