# -*- coding: utf-8 -*-
"""
视觉引擎 - 统一的图像理解接口
整合图像描述、目标检测、文字识别，输出结构化上下文给 LLM
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Union, List, Optional, Dict, Any
from enum import Enum

import numpy as np
from PIL import Image


class VisionModule(Enum):
    """视觉模块枚举"""
    CAPTIONER = "captioner"    # 图像描述
    DETECTOR = "detector"      # 目标检测
    OCR = "ocr"               # 文字识别


@dataclass
class VisionConfig:
    """视觉引擎配置"""
    # 模块开关
    enable_captioner: bool = True   # 启用图像描述
    enable_detector: bool = True    # 启用目标检测
    enable_ocr: bool = True         # 启用 OCR
    
    # 模型配置
    captioner_model: str = "Salesforce/blip-image-captioning-base"
    detector_model: str = "yolov8n"  # nano 版本，最轻量
    ocr_languages: List[str] = field(default_factory=lambda: ["ch_sim", "en"])
    ocr_backend: str = "easyocr"
    
    # 设备配置
    device: str = "auto"             # "auto", "cpu", "cuda"
    use_fp16: bool = True           # 使用半精度
    
    # 检测阈值
    detection_confidence: float = 0.5
    ocr_confidence: float = 0.5


@dataclass
class VisionResult:
    """视觉分析结果"""
    # 原始结果
    caption: Optional[str] = None           # 图像描述
    caption_en: Optional[str] = None        # 英文描述
    objects: Optional[List[str]] = None     # 检测到的物体列表
    objects_detail: Optional[str] = None    # 物体详情
    ocr_text: Optional[str] = None          # OCR 文字
    ocr_lines: Optional[List[str]] = None   # OCR 文字列表
    
    # 元信息
    image_size: Optional[tuple] = None
    modules_used: List[str] = field(default_factory=list)
    
    def to_context(self, style: str = "detailed") -> str:
        """
        转换为 LLM 上下文字符串
        
        Args:
            style: 输出风格
                - "detailed": 详细格式
                - "compact": 紧凑格式
                - "json": JSON 格式
        """
        if style == "json":
            import json
            return json.dumps({
                "caption": self.caption,
                "objects": self.objects,
                "text": self.ocr_text
            }, ensure_ascii=False, indent=2)
        
        elif style == "compact":
            parts = []
            if self.caption:
                parts.append(f"图像: {self.caption}")
            if self.objects:
                parts.append(f"物体: {', '.join(self.objects)}")
            if self.ocr_text:
                parts.append(f"文字: {self.ocr_text}")
            return " | ".join(parts) if parts else "无法分析图像"
        
        else:  # detailed
            lines = ["[图像分析结果]"]
            
            if self.caption:
                lines.append(f"📝 图像描述: {self.caption}")
            
            if self.objects_detail:
                lines.append(f"🔍 检测物体: {self.objects_detail}")
            elif self.objects:
                lines.append(f"🔍 检测物体: {', '.join(self.objects)}")
            
            if self.ocr_text:
                # 截断过长的 OCR 文本
                text = self.ocr_text
                if len(text) > 200:
                    text = text[:200] + "..."
                lines.append(f"📖 图中文字: {text}")
            
            if len(lines) == 1:
                lines.append("⚠️ 未能提取有效信息")
            
            return "\n".join(lines)
    
    def __str__(self) -> str:
        return self.to_context("detailed")


class VisionEngine:
    """
    视觉引擎
    
    整合多个视觉模块，提供统一的图像分析接口
    输出结构化上下文，可直接传给 LLM/Agent
    
    使用示例:
        ```python
        from backend.vision import VisionEngine
        
        # 初始化（可选配置）
        vision = VisionEngine()
        
        # 分析图片
        result = vision.analyze("image.jpg")
        
        # 获取 LLM 上下文
        context = result.to_context()
        print(context)
        
        # 输出:
        # [图像分析结果]
        # 📝 图像描述: a woman sitting at a cafe with a cup of coffee
        # 🔍 检测物体: 人, 杯子, 椅子, 桌子
        # 📖 图中文字: STARBUCKS
        ```
    """
    
    def __init__(self, config: VisionConfig = None):
        """
        初始化视觉引擎
        
        Args:
            config: 配置对象，None 则使用默认配置
        """
        self.config = config or VisionConfig()
        
        # 延迟加载的模块
        self._captioner = None
        self._detector = None
        self._ocr = None
        
        # 加载状态
        self._modules_loaded = set()

    def _get_captioner(self):
        """获取图像描述模块"""
        if self._captioner is None and self.config.enable_captioner:
            from .models.captioner import ImageCaptioner
            self._captioner = ImageCaptioner(
                model_name=self.config.captioner_model,
                device=self.config.device,
                use_fp16=self.config.use_fp16
            )
        return self._captioner

    def _get_detector(self):
        """获取目标检测模块"""
        if self._detector is None and self.config.enable_detector:
            from .models.detector import ObjectDetector
            self._detector = ObjectDetector(
                model_name=self.config.detector_model,
                device=self.config.device,
                confidence_threshold=self.config.detection_confidence
            )
        return self._detector

    def _get_ocr(self):
        """获取 OCR 模块"""
        if self._ocr is None and self.config.enable_ocr:
            from .models.ocr import TextRecognizer
            use_gpu = self.config.device != "cpu"
            self._ocr = TextRecognizer(
                languages=self.config.ocr_languages,
                use_gpu=use_gpu,
                backend=self.config.ocr_backend
            )
        return self._ocr

    def analyze(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        modules: List[VisionModule] = None,
    ) -> VisionResult:
        """
        分析图像
        
        Args:
            image: 图像输入（文件路径、PIL Image 或 numpy 数组）
            modules: 要使用的模块列表，None 则使用所有启用的模块
            
        Returns:
            VisionResult 对象
        """
        result = VisionResult()
        result.modules_used = []
        
        # 加载图像获取尺寸
        if isinstance(image, (str, Path)):
            pil_img = Image.open(image)
            result.image_size = pil_img.size
        elif isinstance(image, Image.Image):
            result.image_size = image.size
        elif isinstance(image, np.ndarray):
            result.image_size = (image.shape[1], image.shape[0])
        
        # 确定要使用的模块
        if modules is None:
            modules = []
            if self.config.enable_captioner:
                modules.append(VisionModule.CAPTIONER)
            if self.config.enable_detector:
                modules.append(VisionModule.DETECTOR)
            if self.config.enable_ocr:
                modules.append(VisionModule.OCR)
        
        # 执行各模块分析
        for module in modules:
            try:
                if module == VisionModule.CAPTIONER:
                    self._run_captioner(image, result)
                elif module == VisionModule.DETECTOR:
                    self._run_detector(image, result)
                elif module == VisionModule.OCR:
                    self._run_ocr(image, result)
            except Exception as e:
                print(f"[Vision] {module.value} 执行失败: {e}")
        
        return result

    def _run_captioner(self, image, result: VisionResult):
        """运行图像描述"""
        captioner = self._get_captioner()
        if captioner:
            caption_result = captioner.generate(image)
            result.caption = caption_result.caption
            result.caption_en = caption_result.caption_en
            result.modules_used.append("captioner")

    def _run_detector(self, image, result: VisionResult):
        """运行目标检测"""
        detector = self._get_detector()
        if detector:
            detect_result = detector.detect(image)
            result.objects = detect_result.get_labels_cn(unique=True)
            result.objects_detail = detect_result.get_summary()
            result.modules_used.append("detector")

    def _run_ocr(self, image, result: VisionResult):
        """运行 OCR"""
        ocr = self._get_ocr()
        if ocr:
            ocr_result = ocr.recognize(image, self.config.ocr_confidence)
            result.ocr_text = ocr_result.get_all_text(separator=" | ")
            result.ocr_lines = ocr_result.get_text_list()
            result.modules_used.append("ocr")

    def analyze_for_llm(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        style: str = "detailed",
    ) -> str:
        """
        分析图像并直接返回 LLM 上下文字符串
        
        Args:
            image: 图像输入
            style: 输出风格 ("detailed", "compact", "json")
            
        Returns:
            可直接传给 LLM 的上下文字符串
        """
        result = self.analyze(image)
        return result.to_context(style)

    def caption(self, image: Union[str, Path, Image.Image, np.ndarray]) -> str:
        """
        仅生成图像描述
        
        Args:
            image: 图像输入
            
        Returns:
            图像描述文本
        """
        captioner = self._get_captioner()
        if captioner:
            return captioner.generate(image).caption
        return ""

    def detect(self, image: Union[str, Path, Image.Image, np.ndarray]) -> List[str]:
        """
        仅进行目标检测
        
        Args:
            image: 图像输入
            
        Returns:
            检测到的物体列表（中文）
        """
        detector = self._get_detector()
        if detector:
            return detector.detect(image).get_labels_cn()
        return []

    def ocr(self, image: Union[str, Path, Image.Image, np.ndarray]) -> str:
        """
        仅进行文字识别
        
        Args:
            image: 图像输入
            
        Returns:
            识别的文字
        """
        ocr = self._get_ocr()
        if ocr:
            return ocr.recognize_simple(image)
        return ""

    def unload(self, modules: List[VisionModule] = None):
        """
        卸载模块释放资源
        
        Args:
            modules: 要卸载的模块列表，None 则卸载所有
        """
        if modules is None:
            modules = [VisionModule.CAPTIONER, VisionModule.DETECTOR, VisionModule.OCR]
        
        for module in modules:
            if module == VisionModule.CAPTIONER and self._captioner:
                self._captioner.unload()
                self._captioner = None
            elif module == VisionModule.DETECTOR and self._detector:
                self._detector.unload()
                self._detector = None
            elif module == VisionModule.OCR and self._ocr:
                self._ocr.unload()
                self._ocr = None
        
        # 清理 GPU 缓存
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except:
            pass

    def get_loaded_modules(self) -> List[str]:
        """获取已加载的模块列表"""
        loaded = []
        if self._captioner and self._captioner.is_loaded():
            loaded.append("captioner")
        if self._detector and self._detector.is_loaded():
            loaded.append("detector")
        if self._ocr and self._ocr.is_loaded():
            loaded.append("ocr")
        return loaded


# 便捷函数
def analyze_image(
    image: Union[str, Path, Image.Image, np.ndarray],
    config: VisionConfig = None
) -> str:
    """
    快速分析图像（一次性使用）
    
    Args:
        image: 图像输入
        config: 配置（可选）
        
    Returns:
        分析结果上下文字符串
    """
    engine = VisionEngine(config)
    result = engine.analyze(image)
    context = result.to_context()
    engine.unload()
    return context
