# -*- coding: utf-8 -*-
"""
视觉分析工具
让 Agent 能够分析图像内容
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

from .base_tool import BaseTool, ToolParameter, ToolResult


class VisionTool(BaseTool):
    """
    视觉分析工具
    
    让 Agent 能够：
    - 分析图像内容
    - 识别图中物体
    - 读取图中文字
    - 获取图像描述
    """
    
    @property
    def name(self) -> str:
        return "vision_analyze"
    
    @property
    def description(self) -> str:
        return """分析图像内容的工具。可以：
1. 生成图像的自然语言描述
2. 检测图像中的物体
3. 识别图像中的文字 (OCR)

使用场景：
- 用户发送了图片需要理解内容
- 需要读取截图中的文字
- 需要知道图片里有什么物体"""

    @property
    def parameters(self):
        return [
            ToolParameter(
                name="image_path",
                type="string",
                description="图像文件的路径",
                required=True
            ),
            ToolParameter(
                name="action",
                type="string",
                description="分析类型: full=完整分析, caption=仅描述, detect=仅检测物体, ocr=仅识别文字",
                required=False,
                enum=["full", "caption", "detect", "ocr"],
                default="full"
            ),
        ]
    
    def __init__(self, **kwargs):
        """
        初始化视觉工具
        
        Args:
            **kwargs: 传递给 VisionEngine 的配置参数
        """
        super().__init__()
        self._vision_engine = None
        self._config_kwargs = kwargs

    def _get_engine(self):
        """延迟加载视觉引擎"""
        if self._vision_engine is None:
            try:
                from backend.vision import VisionEngine, VisionConfig
                
                # 使用轻量配置
                config = VisionConfig(
                    enable_captioner=True,
                    enable_detector=True,
                    enable_ocr=True,
                    detector_model="yolov8n",  # 最轻量
                    device="auto",
                    use_fp16=True,
                )
                
                # 应用自定义配置
                for key, value in self._config_kwargs.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
                
                self._vision_engine = VisionEngine(config)
            except ImportError as e:
                raise ImportError(
                    f"视觉模块导入失败: {e}\n"
                    "请确保已安装依赖: pip install transformers torch ultralytics easyocr"
                )
        
        return self._vision_engine

    def execute(self, image_path: str = None, action: str = "full", **kwargs) -> ToolResult:
        """
        执行图像分析
        
        Args:
            image_path: 图像路径
            action: 分析类型
            
        Returns:
            ToolResult
        """
        if not image_path:
            return ToolResult(success=False, error="缺少必需参数: image_path")
        
        # 验证文件
        if not os.path.exists(image_path):
            return ToolResult(success=False, error=f"图像文件不存在: {image_path}")
        
        # 验证文件类型
        valid_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}
        ext = Path(image_path).suffix.lower()
        if ext not in valid_extensions:
            return ToolResult(success=False, error=f"不支持的图像格式: {ext}")
        
        try:
            engine = self._get_engine()
            
            if action == "caption":
                # 仅生成描述
                caption = engine.caption(image_path)
                return ToolResult(
                    success=True,
                    data={"caption": caption, "context": f"[图像描述] {caption}"}
                )
            
            elif action == "detect":
                # 仅检测物体
                objects = engine.detect(image_path)
                return ToolResult(
                    success=True,
                    data={"objects": objects, "context": f"[检测到的物体] {', '.join(objects) if objects else '无'}"}
                )
            
            elif action == "ocr":
                # 仅识别文字
                text = engine.ocr(image_path)
                return ToolResult(
                    success=True,
                    data={"text": text, "context": f"[图中文字] {text if text else '无'}"}
                )
            
            else:  # full
                # 完整分析
                result = engine.analyze(image_path)
                context = result.to_context()
                
                return ToolResult(
                    success=True,
                    data={
                        "caption": result.caption,
                        "objects": result.objects,
                        "ocr_text": result.ocr_text,
                        "context": context
                    }
                )
        
        except Exception as e:
            return ToolResult(success=False, error=f"图像分析失败: {str(e)}")

    def unload(self):
        """卸载视觉引擎释放资源"""
        if self._vision_engine is not None:
            self._vision_engine.unload()
            self._vision_engine = None


class ScreenshotAnalyzeTool(BaseTool):
    """
    截图分析工具
    
    专门用于分析屏幕截图，优化 OCR 识别
    """
    
    @property
    def name(self) -> str:
        return "screenshot_analyze"
    
    @property
    def description(self) -> str:
        return """分析屏幕截图的工具。专门优化了对截图的处理：
- 读取截图中的文字内容
- 识别截图中的界面元素
- 理解截图显示的信息

使用场景：
- 用户发送了屏幕截图需要理解
- 需要读取截图中的错误信息
- 需要分析截图中显示的内容"""

    @property
    def parameters(self):
        return [
            ToolParameter(
                name="image_path",
                type="string",
                description="截图文件的路径",
                required=True
            ),
        ]
    
    def __init__(self):
        super().__init__()
        self._vision_engine = None

    def _get_engine(self):
        """延迟加载视觉引擎（OCR 优先）"""
        if self._vision_engine is None:
            from backend.vision import VisionEngine, VisionConfig
            
            # 截图分析配置：OCR 为主
            config = VisionConfig(
                enable_captioner=False,   # 截图不需要描述
                enable_detector=True,     # 检测 UI 元素
                enable_ocr=True,          # 主要是 OCR
                detector_model="yolov8n",
                ocr_confidence=0.3,       # 降低阈值，识别更多文字
                device="auto",
            )
            
            self._vision_engine = VisionEngine(config)
        
        return self._vision_engine

    def execute(self, image_path: str = None, **kwargs) -> ToolResult:
        """
        执行截图分析
        
        Args:
            image_path: 截图路径
            
        Returns:
            ToolResult
        """
        if not image_path:
            return ToolResult(success=False, error="缺少必需参数: image_path")
        
        if not os.path.exists(image_path):
            return ToolResult(success=False, error=f"截图文件不存在: {image_path}")
        
        try:
            engine = self._get_engine()
            result = engine.analyze(image_path)
            
            # 构建截图专用的上下文
            lines = ["[截图分析结果]"]
            
            if result.ocr_text:
                lines.append(f"截图内容:")
                # 分行显示 OCR 结果
                for line in result.ocr_lines or []:
                    if line.strip():
                        lines.append(f"   {line}")
            
            if result.objects:
                lines.append(f"界面元素: {', '.join(result.objects)}")
            
            if len(lines) == 1:
                lines.append("未能识别截图内容")
            
            context = "\n".join(lines)
            
            return ToolResult(
                success=True,
                data={
                    "text": result.ocr_text,
                    "objects": result.objects,
                    "context": context
                }
            )
        
        except Exception as e:
            return ToolResult(success=False, error=f"截图分析失败: {str(e)}")

    def unload(self):
        """卸载视觉引擎"""
        if self._vision_engine is not None:
            self._vision_engine.unload()
            self._vision_engine = None
