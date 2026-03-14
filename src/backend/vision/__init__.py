# -*- coding: utf-8 -*-
"""
视觉理解模块
提供图像描述、目标检测、文字识别功能

使用方法:
    from backend.vision import VisionEngine
    
    # 初始化引擎
    vision = VisionEngine()
    
    # 分析图片，获取结构化上下文
    context = vision.analyze("image.jpg")
    print(context)
    
    # 输出示例:
    # [图像分析结果]
    # 📝 图像描述: 一个女孩在咖啡厅里看书
    # 🔍 检测物体: person, book, cup, table
    # 📖 图中文字: STARBUCKS, WiFi: guest
"""

from .vision_engine import VisionEngine, VisionConfig

__all__ = ["VisionEngine", "VisionConfig"]
__version__ = "1.0.0"
