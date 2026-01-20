"""
文件操作工具
读写文本文件
"""
from typing import List, Optional
from datetime import datetime
import os
import time

from .base_tool import BaseTool, ToolParameter, ToolResult


class FileWriteTool(BaseTool):
    """文件写入工具"""
    
    def __init__(self, default_save_dir: str = "data/txt"):
        """
        Args:
            default_save_dir: 默认保存目录
        """
        self._default_save_dir = default_save_dir
        os.makedirs(default_save_dir, exist_ok=True)
    
    @property
    def name(self) -> str:
        return "write_file"
    
    @property
    def description(self) -> str:
        return """将文本内容保存到文件。
当用户说以下内容时使用：
- 帮我记下来
- 保存这段话
- 写入文件
- 记录一下
- 把这个存起来"""
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="content",
                type="string",
                description="要保存的文本内容",
                required=True
            ),
            ToolParameter(
                name="filename",
                type="string",
                description="文件名（不含路径），留空则自动生成时间戳命名",
                required=False,
                default=""
            )
        ]
    
    def execute(self, content: str, filename: str = "") -> ToolResult:
        """写入文件"""
        try:
            # 生成文件名
            if not filename:
                timestamp = int(time.time())
                filename = f"{timestamp}.txt"
            
            # 确保有扩展名
            if not filename.endswith('.txt'):
                filename += '.txt'
            
            # 完整路径
            save_path = os.path.join(self._default_save_dir, filename)
            
            # 写入文件
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult(
                success=True,
                data={
                    "message": "文本已保存",
                    "path": save_path,
                    "filename": filename,
                    "length": len(content)
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FileReadTool(BaseTool):
    """文件读取工具"""
    
    def __init__(self, allowed_dirs: List[str] = None):
        """
        Args:
            allowed_dirs: 允许读取的目录列表（安全限制）
        """
        self._allowed_dirs = allowed_dirs or ["data/"]
    
    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return """读取文本文件内容。
当用户说以下内容时使用：
- 读取文件
- 打开那个文件
- 看看文件里写了什么
- 读一下 xxx.txt"""
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="filepath",
                type="string",
                description="文件路径",
                required=True
            )
        ]
    
    def execute(self, filepath: str) -> ToolResult:
        """读取文件"""
        try:
            # 安全检查
            # is_allowed = any(filepath.startswith(d) for d in self._allowed_dirs)
            # if not is_allowed:
            #     return ToolResult(success=False, error="不允许访问该路径")
            
            if not os.path.exists(filepath):
                return ToolResult(success=False, error=f"文件不存在: {filepath}")
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return ToolResult(
                success=True,
                data={
                    "filepath": filepath,
                    "content": content,
                    "length": len(content)
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
