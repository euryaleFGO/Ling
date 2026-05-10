# -*- coding: utf-8 -*-
"""
视觉语言模型 (VLM) 模块
支持 SmolVLM-256M 等轻量级 VLM 模型
"""

import logging
import os
from pathlib import Path
from typing import Union, Optional, List
from dataclasses import dataclass

import torch

logger = logging.getLogger(__name__)
import numpy as np
from PIL import Image
from transformers import AutoProcessor, AutoModelForVision2Seq


@dataclass
class VLMResult:
    """VLM 分析结果"""
    text: str                    # 生成的文本
    confidence: float = 1.0      # 置信度
    model_name: str = ""         # 使用的模型名称
    
    def __str__(self) -> str:
        return self.text


class VLMModel:
    """
    视觉语言模型 (Vision-Language Model)
    
    支持的模型:
    - SmolVLM-256M: 轻量级 VLM，256M 参数
    - SmolVLM-500M: 中等规模 VLM，500M 参数
    - 其他兼容的 HuggingFace VLM 模型
    
    使用示例:
        ```python
        from backend.vision.models.vlm import VLMModel
        
        # 初始化模型
        vlm = VLMModel(
            model_path="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M"
        )
        
        # 分析图像
        result = vlm.generate(
            image="image.jpg",
            prompt="描述这张图片"
        )
        print(result.text)
        
        # 多轮对话
        result = vlm.chat(
            image="image.jpg",
            messages=[
                {"role": "user", "content": "这张图片里有什么？"},
                {"role": "assistant", "content": "图片中有一只猫"},
                {"role": "user", "content": "猫是什么颜色的？"}
            ]
        )
        ```
    """
    
    def __init__(
        self,
        model_path: Union[str, Path] = None,
        model_name: str = "SmolVLM-256M",
        device: str = "auto",
        use_fp16: bool = True,
        max_new_tokens: int = 512,
    ):
        """
        初始化 VLM 模型
        
        Args:
            model_path: 模型路径（本地路径或 HuggingFace 模型 ID）
            model_name: 模型名称（用于标识）
            device: 设备 ("auto", "cpu", "cuda", "cuda:0" 等)
            use_fp16: 是否使用半精度（FP16）
            max_new_tokens: 最大生成 token 数
        """
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        
        # 确定设备 (Fix 6.7: check free GPU memory to avoid OOM on RTX 2050 4GB)
        if device == "auto":
            if torch.cuda.is_available():
                try:
                    free, total = torch.cuda.mem_get_info()
                    if free > 1 * 1024**3:  # Need at least 1GB free
                        self.device = "cuda"
                    else:
                        self.device = "cpu"
                        logger.warning(
                            "Insufficient GPU memory (%.1fMB free), using CPU",
                            free / 1024**2
                        )
                except Exception:
                    self.device = "cuda"
            else:
                self.device = "cpu"
        else:
            self.device = device
        
        self.use_fp16 = use_fp16 and self.device != "cpu"
        
        # 确定模型路径
        if model_path is None:
            # 默认路径
            default_base = Path(os.environ.get("LIYING_MODELS_DIR", "models"))
            model_path = default_base / "Vision" / "VLM" / model_name
        
        self.model_path = Path(model_path)
        
        # 延迟加载
        self.processor = None
        self.model = None
        self._loaded = False
    
    def load(self):
        """加载模型"""
        if self._loaded:
            return
        
        print(f"[VLM] 加载模型: {self.model_path}")
        
        try:
            # Fix 6.13: warn about trust_remote_code
            logger.warning(
                "Loading model with trust_remote_code=True (local_files_only=True). "
                "This allows arbitrary code execution during model loading."
            )

            # 加载 processor
            self.processor = AutoProcessor.from_pretrained(
                str(self.model_path),
                trust_remote_code=True,
                local_files_only=True,
            )

            # 加载模型
            self.model = AutoModelForVision2Seq.from_pretrained(
                str(self.model_path),
                torch_dtype=torch.float16 if self.use_fp16 else torch.float32,
                trust_remote_code=True,
                local_files_only=True,
                device_map=self.device if self.device != "cpu" else None
            )
            
            # CPU 模式下手动移动到设备
            if self.device == "cpu":
                self.model = self.model.to(self.device)
            
            self.model.eval()
            self._loaded = True
            
            print(f"[VLM] 模型加载完成 (设备: {self.device}, FP16: {self.use_fp16})")
            
        except Exception as e:
            print(f"[VLM] 模型加载失败: {e}")
            raise
    
    def unload(self):
        """卸载模型释放资源"""
        if self.model:
            del self.model
            self.model = None
        
        if self.processor:
            del self.processor
            self.processor = None
        
        self._loaded = False
        
        # 清理 GPU 缓存
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        print(f"[VLM] 模型已卸载")
    
    def is_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._loaded
    
    def _load_image(self, image: Union[str, Path, Image.Image, np.ndarray]) -> Image.Image:
        """加载图像为 PIL Image"""
        if isinstance(image, (str, Path)):
            # Fix 6.14: open-convert-copy-close to avoid PIL file handle leak
            pil_img = Image.open(image)
            try:
                return pil_img.convert("RGB").copy()
            finally:
                pil_img.close()
        elif isinstance(image, Image.Image):
            return image.convert("RGB")
        elif isinstance(image, np.ndarray):
            return Image.fromarray(image).convert("RGB")
        else:
            raise ValueError(f"不支持的图像类型: {type(image)}")
    
    def generate(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        prompt: str = "描述这张图片",
        max_new_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> VLMResult:
        """
        生成图像描述或回答问题
        
        Args:
            image: 图像输入
            prompt: 提示词
            max_new_tokens: 最大生成 token 数（None 使用默认值）
            temperature: 温度参数（控制随机性）
            top_p: Top-p 采样参数
            
        Returns:
            VLMResult 对象
        """
        # 确保模型已加载
        if not self._loaded:
            self.load()
        
        # 加载图像
        pil_image = self._load_image(image)
        
        # 构建输入
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        
        # 处理输入
        prompt_text = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True
        )
        
        inputs = self.processor(
            text=prompt_text,
            images=[pil_image],
            return_tensors="pt"
        )
        
        # 移动到设备
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # 生成 (Fix 6.15: guard against temperature=0 division by zero)
        safe_temperature = max(temperature, 0.01)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens or self.max_new_tokens,
                temperature=safe_temperature,
                top_p=top_p,
                do_sample=True,
            )
        
        # 解码
        generated_text = self.processor.decode(
            outputs[0],
            skip_special_tokens=True
        )
        
        # 提取生成的部分（去除输入提示）
        # SmolVLM 的输出格式: <|im_start|>user\n...<|im_end|>\n<|im_start|>assistant\n{生成内容}<|im_end|>
        if "assistant" in generated_text:
            generated_text = generated_text.split("assistant")[-1]
            generated_text = generated_text.replace("<|im_end|>", "").strip()
        
        return VLMResult(
            text=generated_text,
            model_name=self.model_name
        )
    
    def chat(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        messages: List[dict],
        max_new_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> VLMResult:
        """
        多轮对话
        
        Args:
            image: 图像输入
            messages: 对话历史，格式:
                [
                    {"role": "user", "content": "问题1"},
                    {"role": "assistant", "content": "回答1"},
                    {"role": "user", "content": "问题2"}
                ]
            max_new_tokens: 最大生成 token 数
            temperature: 温度参数
            top_p: Top-p 采样参数
            
        Returns:
            VLMResult 对象
        """
        # 确保模型已加载
        if not self._loaded:
            self.load()
        
        # 加载图像
        pil_image = self._load_image(image)
        
        # 构建完整的消息列表（第一条消息包含图像）
        full_messages = []
        for i, msg in enumerate(messages):
            if i == 0 and msg["role"] == "user":
                # 第一条用户消息包含图像
                full_messages.append({
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": msg["content"]}
                    ]
                })
            else:
                # 其他消息只包含文本
                full_messages.append({
                    "role": msg["role"],
                    "content": [{"type": "text", "text": msg["content"]}]
                })
        
        # 处理输入
        prompt_text = self.processor.apply_chat_template(
            full_messages,
            add_generation_prompt=True
        )
        
        inputs = self.processor(
            text=prompt_text,
            images=[pil_image],
            return_tensors="pt"
        )
        
        # 移动到设备
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # 生成 (Fix 6.15: guard against temperature=0 division by zero)
        safe_temperature = max(temperature, 0.01)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens or self.max_new_tokens,
                temperature=safe_temperature,
                top_p=top_p,
                do_sample=True,
            )
        
        # 解码
        generated_text = self.processor.decode(
            outputs[0],
            skip_special_tokens=True
        )
        
        # 提取生成的部分
        if "assistant" in generated_text:
            parts = generated_text.split("assistant")
            if len(parts) > 1:
                generated_text = parts[-1].replace("<|im_end|>", "").strip()
        
        return VLMResult(
            text=generated_text,
            model_name=self.model_name
        )
    
    def describe_image(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        language: str = "zh"
    ) -> str:
        """
        快速生成图像描述
        
        Args:
            image: 图像输入
            language: 语言 ("zh" 中文, "en" 英文)
            
        Returns:
            图像描述文本
        """
        if language == "zh":
            prompt = "请详细描述这张图片的内容"
        else:
            prompt = "Describe this image in detail"
        
        result = self.generate(image, prompt)
        return result.text
    
    def answer_question(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        question: str
    ) -> str:
        """
        回答关于图像的问题
        
        Args:
            image: 图像输入
            question: 问题
            
        Returns:
            回答文本
        """
        result = self.generate(image, question)
        return result.text


# 便捷函数
def analyze_with_vlm(
    image: Union[str, Path, Image.Image, np.ndarray],
    prompt: str = "描述这张图片",
    model_path: Union[str, Path] = None,
    device: str = "auto"
) -> str:
    """
    使用 VLM 快速分析图像（一次性使用）
    
    Args:
        image: 图像输入
        prompt: 提示词
        model_path: 模型路径
        device: 设备
        
    Returns:
        生成的文本
    """
    vlm = VLMModel(model_path=model_path, device=device)
    result = vlm.generate(image, prompt)
    vlm.unload()
    return result.text
