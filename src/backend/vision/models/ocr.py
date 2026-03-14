# -*- coding: utf-8 -*-
"""
文字识别模块 (OCR)
使用 EasyOCR 或 PaddleOCR 识别图像中的文字
"""

import os
from pathlib import Path
from typing import Union, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class TextBox:
    """单个文字区域"""
    text: str                    # 识别的文字
    confidence: float            # 置信度
    bbox: List[List[int]]        # 边界框 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    
    @property
    def bbox_xyxy(self) -> Tuple[int, int, int, int]:
        """获取 (x1, y1, x2, y2) 格式的边界框"""
        xs = [p[0] for p in self.bbox]
        ys = [p[1] for p in self.bbox]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class OCRResult:
    """OCR 结果"""
    text_boxes: List[TextBox]    # 所有文字区域
    image_size: Tuple[int, int]  # 图像尺寸 (width, height)
    
    def get_all_text(self, separator: str = "\n") -> str:
        """获取所有识别的文字"""
        return separator.join(box.text for box in self.text_boxes if box.text.strip())
    
    def get_text_list(self) -> List[str]:
        """获取文字列表"""
        return [box.text for box in self.text_boxes if box.text.strip()]
    
    def filter_by_confidence(self, threshold: float) -> "OCRResult":
        """按置信度过滤"""
        filtered = [box for box in self.text_boxes if box.confidence >= threshold]
        return OCRResult(text_boxes=filtered, image_size=self.image_size)


class TextRecognizer:
    """
    文字识别器
    
    默认使用 EasyOCR（更轻量，无需 PaddlePaddle）
    支持中英文识别
    """
    
    def __init__(
        self,
        languages: List[str] = None,
        use_gpu: bool = True,
        backend: str = "easyocr",  # "easyocr" 或 "paddleocr"
    ):
        """
        初始化文字识别器
        
        Args:
            languages: 要识别的语言列表，默认 ["ch_sim", "en"]（简体中文+英文）
            use_gpu: 是否使用 GPU
            backend: 后端选择 ("easyocr" 或 "paddleocr")
        """
        if languages is None:
            languages = ["ch_sim", "en"]
        
        self.languages = languages
        self.use_gpu = use_gpu
        self.backend = backend
        self._reader = None
        self._loaded = False

    def _load_model(self):
        """延迟加载模型"""
        if self._loaded:
            return
        
        if self.backend == "easyocr":
            self._load_easyocr()
        elif self.backend == "paddleocr":
            self._load_paddleocr()
        else:
            raise ValueError(f"不支持的后端: {self.backend}")
        
        self._loaded = True

    def _load_easyocr(self):
        """加载 EasyOCR"""
        try:
            import easyocr
        except ImportError:
            raise ImportError(
                "请安装 easyocr:\n"
                "pip install easyocr"
            )
        
        print(f"[Vision] 加载 OCR 模型 (EasyOCR)")
        print(f"[Vision] 语言: {self.languages}")
        
        # EasyOCR 语言映射
        lang_map = {
            "ch_sim": "ch_sim",
            "ch_tra": "ch_tra", 
            "en": "en",
            "ja": "ja",
            "ko": "ko",
        }
        
        langs = [lang_map.get(l, l) for l in self.languages]
        
        self._reader = easyocr.Reader(
            langs,
            gpu=self.use_gpu,
            verbose=False
        )
        
        print("[Vision] OCR 模型加载完成")

    def _load_paddleocr(self):
        """加载 PaddleOCR"""
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            raise ImportError(
                "请安装 paddleocr:\n"
                "pip install paddlepaddle paddleocr"
            )
        
        print(f"[Vision] 加载 OCR 模型 (PaddleOCR)")
        
        # 确定语言
        lang = "ch" if "ch_sim" in self.languages else "en"
        
        self._reader = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=self.use_gpu,
            show_log=False
        )
        
        print("[Vision] OCR 模型加载完成")

    def recognize(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        confidence_threshold: float = 0.5,
    ) -> OCRResult:
        """
        识别图像中的文字
        
        Args:
            image: 图像输入
            confidence_threshold: 置信度阈值
            
        Returns:
            OCRResult 对象
        """
        self._load_model()
        
        # 转换图像格式
        if isinstance(image, (str, Path)):
            image_path = str(image)
            pil_img = Image.open(image)
            img_size = pil_img.size
            img_array = np.array(pil_img)
        elif isinstance(image, Image.Image):
            img_size = image.size
            img_array = np.array(image)
            image_path = None
        elif isinstance(image, np.ndarray):
            img_size = (image.shape[1], image.shape[0])
            img_array = image
            image_path = None
        else:
            raise TypeError(f"不支持的图像类型: {type(image)}")
        
        # 执行 OCR
        if self.backend == "easyocr":
            return self._recognize_easyocr(img_array, img_size, confidence_threshold)
        else:
            return self._recognize_paddleocr(img_array, img_size, confidence_threshold)

    def _recognize_easyocr(
        self, 
        img_array: np.ndarray, 
        img_size: Tuple[int, int],
        confidence_threshold: float
    ) -> OCRResult:
        """使用 EasyOCR 识别"""
        results = self._reader.readtext(img_array)
        
        text_boxes = []
        for bbox, text, conf in results:
            if conf >= confidence_threshold:
                # EasyOCR 返回的 bbox 格式: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text_boxes.append(TextBox(
                    text=text,
                    confidence=conf,
                    bbox=[[int(p[0]), int(p[1])] for p in bbox]
                ))
        
        return OCRResult(text_boxes=text_boxes, image_size=img_size)

    def _recognize_paddleocr(
        self, 
        img_array: np.ndarray, 
        img_size: Tuple[int, int],
        confidence_threshold: float
    ) -> OCRResult:
        """使用 PaddleOCR 识别"""
        results = self._reader.ocr(img_array, cls=True)
        
        text_boxes = []
        if results and results[0]:
            for line in results[0]:
                bbox, (text, conf) = line
                if conf >= confidence_threshold:
                    text_boxes.append(TextBox(
                        text=text,
                        confidence=conf,
                        bbox=[[int(p[0]), int(p[1])] for p in bbox]
                    ))
        
        return OCRResult(text_boxes=text_boxes, image_size=img_size)

    def recognize_simple(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
    ) -> str:
        """
        简单识别，直接返回所有文字
        
        Args:
            image: 图像输入
            
        Returns:
            识别的所有文字（换行分隔）
        """
        result = self.recognize(image)
        return result.get_all_text()

    def unload(self):
        """卸载模型释放内存"""
        if self._reader is not None:
            del self._reader
            self._reader = None
            self._loaded = False
            
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except:
                pass
            
            print("[Vision] OCR 模型已卸载")

    def is_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._loaded
