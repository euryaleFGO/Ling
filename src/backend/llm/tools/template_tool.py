"""
自定义工具模板
复制此文件并修改来创建新工具
"""
from typing import List, Optional
from .base_tool import BaseTool, ToolParameter, ToolResult


class MyCustomTool(BaseTool):
    """
    自定义工具
    
    使用方法：
    1. 修改类名
    2. 实现 name, description, parameters, execute
    3. 在 __init__.py 中导出
    4. 在 agent.py 的 _setup_tools() 中注册
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化工具
        
        Args:
            api_key: 如果需要调用外部 API，在这里传入密钥
        """
        self._api_key = api_key
    
    @property
    def name(self) -> str:
        """工具名称（唯一标识，英文小写+下划线）"""
        return "my_custom_tool"
    
    @property
    def description(self) -> str:
        """
        工具描述 - 非常重要！
        
        LLM 根据这个描述判断什么时候调用此工具。
        写清楚：
        1. 这个工具是做什么的
        2. 什么情况下应该使用
        3. 举几个使用场景的例子
        """
        return """这是一个示例工具。
当用户询问以下问题时使用此工具：
- 示例问题1
- 示例问题2
- 示例问题3"""
    
    @property
    def parameters(self) -> List[ToolParameter]:
        """
        参数定义
        
        type 支持: string, number, boolean, array, object
        """
        return [
            ToolParameter(
                name="param1",
                type="string",
                description="参数1的描述",
                required=True  # 必填参数
            ),
            ToolParameter(
                name="param2",
                type="number",
                description="参数2的描述",
                required=False,  # 可选参数
                default=10  # 默认值
            ),
            ToolParameter(
                name="param3",
                type="string",
                description="参数3的描述（枚举类型）",
                required=False,
                enum=["option1", "option2", "option3"],  # 限定选项
                default="option1"
            ),
        ]
    
    def execute(self, param1: str, param2: int = 10, param3: str = "option1") -> ToolResult:
        """
        执行工具
        
        Args:
            param1: 参数1
            param2: 参数2
            param3: 参数3
            
        Returns:
            ToolResult: 包含 success, data, error
        """
        try:
            # ========== 在这里实现你的逻辑 ==========
            
            # 示例：调用外部 API
            # if self._api_key:
            #     response = requests.get(
            #         "https://api.example.com/data",
            #         params={"query": param1},
            #         headers={"Authorization": f"Bearer {self._api_key}"}
            #     )
            #     data = response.json()
            
            # 示例：本地计算
            result = {
                "input": param1,
                "processed": f"处理结果: {param1}",
                "count": param2,
                "mode": param3
            }
            
            # ========================================
            
            return ToolResult(success=True, data=result)
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============ 更多示例 ============

class CalculatorTool(BaseTool):
    """计算器工具示例"""
    
    @property
    def name(self) -> str:
        return "calculator"
    
    @property
    def description(self) -> str:
        return """执行数学计算。
当用户需要计算数学表达式时使用，如：
- 123 + 456 等于多少？
- 计算 15% 的税
- 100 的平方根"""
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="expression",
                type="string",
                description="数学表达式，如: 1+2*3, sqrt(16), 100*0.15",
                required=True
            )
        ]
    
    def execute(self, expression: str) -> ToolResult:
        try:
            # 安全的数学计算（只允许数字和基本运算符）
            import math
            allowed = set('0123456789+-*/.() ')
            allowed_funcs = {'sqrt': math.sqrt, 'abs': abs, 'round': round}
            
            # 简单表达式直接计算
            if all(c in allowed for c in expression):
                result = eval(expression)
                return ToolResult(success=True, data={"expression": expression, "result": result})
            
            return ToolResult(success=False, error="不支持的表达式")
        except Exception as e:
            return ToolResult(success=False, error=f"计算错误: {e}")
