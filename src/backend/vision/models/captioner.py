# -*- coding: utf-8 -*-
"""
图像描述生成模块
使用 BLIP 模型生成图像的自然语言描述
"""

import os
from pathlib import Path
from typing import Union, Optional
from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class CaptionResult:
    """图像描述结果"""
    caption: str           # 主描述
    caption_en: str = ""   # 英文描述（如果有）
    confidence: float = 1.0


class ImageCaptioner:
    """
    图像描述生成器
    
    使用 BLIP 模型生成图像描述
    支持 CPU 和 GPU 推理
    """
    
    def __init__(
        self,
        model_name: str = "Salesforce/blip-image-captioning-base",
        device: str = "auto",
        use_fp16: bool = True,
    ):
        """
        初始化图像描述生成器
        
        Args:
            model_name: 模型名称或本地路径
                - "Salesforce/blip-image-captioning-base" (~1GB, 推荐)
                - "Salesforce/blip-image-captioning-large" (~1.8GB, 更准确)
            device: 设备 ("auto", "cpu", "cuda")
            use_fp16: 是否使用半精度（节省显存）
        """
        self.model_name = model_name
        self.use_fp16 = use_fp16
        self._model = None
        self._processor = None
        self._device = None
        
        # 确定设备
        if device == "auto":
            try:
                import torch
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                self._device = "cpu"
        else:
            self._device = device
        
        self._loaded = False

    def _load_model(self):
        """延迟加载模型"""
        if self._loaded:
            return
        
        try:
            from transformers import BlipProcessor, BlipForConditionalGeneration
            import torch
        except ImportError:
            raise ImportError(
                "请安装 transformers 和 torch:\n"
                "pip install transformers torch torchvision"
            )
        
        print(f"[Vision] 加载图像描述模型: {self.model_name}")
        print(f"[Vision] 使用设备: {self._device}")
        
        self._processor = BlipProcessor.from_pretrained(self.model_name)
        
        # 根据设备和配置加载模型
        if self._device == "cuda" and self.use_fp16:
            self._model = BlipForConditionalGeneration.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16
            ).to(self._device)
        else:
            self._model = BlipForConditionalGeneration.from_pretrained(
                self.model_name
            ).to(self._device)
        
        self._model.eval()
        self._loaded = True
        print("[Vision] 图像描述模型加载完成")

    def generate(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        max_length: int = 50,
        num_beams: int = 4,
    ) -> CaptionResult:
        """
        生成图像描述
        
        Args:
            image: 图像输入（文件路径、PIL Image 或 numpy 数组）
            max_length: 最大生成长度
            num_beams: Beam search 数量
            
        Returns:
            CaptionResult 对象
        """
        self._load_model()
        
        import torch
        
        # 加载图像
        if isinstance(image, (str, Path)):
            image = Image.open(image).convert("RGB")
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(image).convert("RGB")
        elif not isinstance(image, Image.Image):
            raise TypeError(f"不支持的图像类型: {type(image)}")
        
        # 处理图像
        inputs = self._processor(image, return_tensors="pt").to(self._device)
        
        if self._device == "cuda" and self.use_fp16:
            inputs["pixel_values"] = inputs["pixel_values"].half()
        
        # 生成描述
        with torch.no_grad():
            output = self._model.generate(
                **inputs,
                max_length=max_length,
                num_beams=num_beams,
            )
        
        caption = self._processor.decode(output[0], skip_special_tokens=True)
        
        return CaptionResult(
            caption=caption,
            caption_en=caption,  # BLIP 默认输出英文
            confidence=1.0
        )

    def generate_chinese(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        max_length: int = 50,
    ) -> CaptionResult:
        """
        生成中文图像描述
        
        注意: BLIP 原生不支持中文，这里使用翻译或中文模型
        如果需要原生中文支持，建议使用 chinese-clip 或其他中文模型
        """
        # 先生成英文描述
        result = self.generate(image, max_length)
        
        # 简单的英文转中文（实际项目中可以调用翻译 API）
        # 这里只是占位，保持英文
        result.caption = result.caption_en
        
        return result

    def unload(self):
        """卸载模型释放显存"""
        if self._model is not None:
            del self._model
            del self._processor
            self._model = None
            self._processor = None
            self._loaded = False
            
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except:
                pass
            
            print("[Vision] 图像描述模型已卸载")

    def is_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._loaded
