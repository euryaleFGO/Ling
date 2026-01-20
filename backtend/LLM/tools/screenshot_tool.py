"""
截图工具
截取当前屏幕并保存
"""
from typing import List, Optional
from datetime import datetime
import os

from .base_tool import BaseTool, ToolParameter, ToolResult


class ScreenshotTool(BaseTool):
    """屏幕截图工具"""
    
    def __init__(self, default_save_dir: str = "data/screenshots"):
        """
        Args:
            default_save_dir: 默认保存目录
        """
        self._default_save_dir = default_save_dir
        # 确保目录存在
        os.makedirs(default_save_dir, exist_ok=True)
    
    @property
    def name(self) -> str:
        return "screenshot"
    
    @property
    def description(self) -> str:
        return """截取当前屏幕并保存为图片。
当用户说以下内容时使用：
- 截个图
- 帮我截屏
- 保存一下屏幕
- 看看我的屏幕"""
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="filename",
                type="string",
                description="保存的文件名（不含路径），留空则自动生成时间戳命名",
                required=False,
                default=""
            )
        ]
    
    def execute(self, filename: str = "") -> ToolResult:
        """执行截图"""
        try:
            import pyautogui
            
            # 生成文件名
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.png"
            
            # 确保有扩展名
            if not filename.endswith(('.png', '.jpg', '.jpeg')):
                filename += '.png'
            
            # 完整路径
            save_path = os.path.join(self._default_save_dir, filename)
            
            # 截图并保存
            screenshot = pyautogui.screenshot()
            screenshot.save(save_path)
            
            return ToolResult(
                success=True,
                data={
                    "message": "截图已保存",
                    "path": save_path,
                    "filename": filename
                }
            )
        except ImportError:
            return ToolResult(
                success=False,
                error="需要安装 pyautogui: pip install pyautogui"
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
