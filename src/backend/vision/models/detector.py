# -*- coding: utf-8 -*-
"""
目标检测模块
使用 YOLOv8 进行目标检测
"""

import os
from pathlib import Path
from typing import Union, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class Detection:
    """单个检测结果"""
    label: str           # 类别名称
    confidence: float    # 置信度
    bbox: Tuple[int, int, int, int]  # 边界框 (x1, y1, x2, y2)
    
    @property
    def label_cn(self) -> str:
        """获取中文标签"""
        return COCO_LABELS_CN.get(self.label, self.label)


@dataclass
class DetectionResult:
    """检测结果"""
    detections: List[Detection]  # 所有检测
    image_size: Tuple[int, int]  # 图像尺寸 (width, height)
    
    def get_labels(self, unique: bool = True) -> List[str]:
        """获取检测到的标签列表"""
        labels = [d.label for d in self.detections]
        return list(set(labels)) if unique else labels
    
    def get_labels_cn(self, unique: bool = True) -> List[str]:
        """获取中文标签列表"""
        labels = [d.label_cn for d in self.detections]
        return list(set(labels)) if unique else labels
    
    def get_summary(self) -> str:
        """获取检测摘要"""
        from collections import Counter
        counter = Counter(d.label_cn for d in self.detections)
        parts = [f"{label}({count}个)" if count > 1 else label 
                 for label, count in counter.items()]
        return ", ".join(parts) if parts else "无"
    
    def filter_by_confidence(self, threshold: float) -> "DetectionResult":
        """按置信度过滤"""
        filtered = [d for d in self.detections if d.confidence >= threshold]
        return DetectionResult(detections=filtered, image_size=self.image_size)


# COCO 数据集类别的中文映射
COCO_LABELS_CN = {
    "person": "人",
    "bicycle": "自行车",
    "car": "汽车",
    "motorcycle": "摩托车",
    "airplane": "飞机",
    "bus": "公交车",
    "train": "火车",
    "truck": "卡车",
    "boat": "船",
    "traffic light": "交通灯",
    "fire hydrant": "消防栓",
    "stop sign": "停车标志",
    "parking meter": "停车计时器",
    "bench": "长椅",
    "bird": "鸟",
    "cat": "猫",
    "dog": "狗",
    "horse": "马",
    "sheep": "羊",
    "cow": "牛",
    "elephant": "大象",
    "bear": "熊",
    "zebra": "斑马",
    "giraffe": "长颈鹿",
    "backpack": "背包",
    "umbrella": "雨伞",
    "handbag": "手提包",
    "tie": "领带",
    "suitcase": "行李箱",
    "frisbee": "飞盘",
    "skis": "滑雪板",
    "snowboard": "滑雪板",
    "sports ball": "运动球",
    "kite": "风筝",
    "baseball bat": "棒球棒",
    "baseball glove": "棒球手套",
    "skateboard": "滑板",
    "surfboard": "冲浪板",
    "tennis racket": "网球拍",
    "bottle": "瓶子",
    "wine glass": "酒杯",
    "cup": "杯子",
    "fork": "叉子",
    "knife": "刀",
    "spoon": "勺子",
    "bowl": "碗",
    "banana": "香蕉",
    "apple": "苹果",
    "sandwich": "三明治",
    "orange": "橙子",
    "broccoli": "西兰花",
    "carrot": "胡萝卜",
    "hot dog": "热狗",
    "pizza": "披萨",
    "donut": "甜甜圈",
    "cake": "蛋糕",
    "chair": "椅子",
    "couch": "沙发",
    "potted plant": "盆栽",
    "bed": "床",
    "dining table": "餐桌",
    "toilet": "马桶",
    "tv": "电视",
    "laptop": "笔记本电脑",
    "mouse": "鼠标",
    "remote": "遥控器",
    "keyboard": "键盘",
    "cell phone": "手机",
    "microwave": "微波炉",
    "oven": "烤箱",
    "toaster": "烤面包机",
    "sink": "水槽",
    "refrigerator": "冰箱",
    "book": "书",
    "clock": "时钟",
    "vase": "花瓶",
    "scissors": "剪刀",
    "teddy bear": "泰迪熊",
    "hair drier": "吹风机",
    "toothbrush": "牙刷",
}


class ObjectDetector:
    """
    目标检测器
    
    使用 YOLOv8 进行目标检测
    支持 CPU 和 GPU 推理
    """
    
    def __init__(
        self,
        model_name: str = "yolov8n",
        device: str = "auto",
        confidence_threshold: float = 0.5,
    ):
        """
        初始化目标检测器
        
        Args:
            model_name: 模型名称
                - "yolov8n": Nano 版本，最快最小 (~6MB)
                - "yolov8s": Small 版本 (~22MB)
                - "yolov8m": Medium 版本 (~50MB)
            device: 设备 ("auto", "cpu", "cuda", "0", "1" 等)
            confidence_threshold: 默认置信度阈值
        """
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self._model = None
        self._device = device
        self._loaded = False

    def _load_model(self):
        """延迟加载模型"""
        if self._loaded:
            return
        
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError(
                "请安装 ultralytics:\n"
                "pip install ultralytics"
            )
        
        print(f"[Vision] 加载目标检测模型: {self.model_name}")
        
        # 加载模型
        self._model = YOLO(f"{self.model_name}.pt")
        
        # 设置设备
        if self._device == "auto":
            pass  # YOLO 会自动选择
        elif self._device != "cpu":
            self._model.to(self._device)
        
        self._loaded = True
        print("[Vision] 目标检测模型加载完成")

    def detect(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        confidence: float = None,
        classes: List[int] = None,
    ) -> DetectionResult:
        """
        检测图像中的目标
        
        Args:
            image: 图像输入
            confidence: 置信度阈值（None 则使用默认值）
            classes: 要检测的类别 ID 列表（None 则检测所有）
            
        Returns:
            DetectionResult 对象
        """
        self._load_model()
        
        conf = confidence if confidence is not None else self.confidence_threshold
        
        # 获取图像尺寸
        if isinstance(image, (str, Path)):
            pil_img = Image.open(image)
            img_size = pil_img.size
        elif isinstance(image, Image.Image):
            img_size = image.size
        elif isinstance(image, np.ndarray):
            img_size = (image.shape[1], image.shape[0])
        else:
            raise TypeError(f"不支持的图像类型: {type(image)}")
        
        # 运行检测
        results = self._model(
            image,
            conf=conf,
            classes=classes,
            verbose=False
        )
        
        # 解析结果
        detections = []
        if len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                bbox = boxes.xyxy[i].cpu().numpy().astype(int)
                conf_score = float(boxes.conf[i].cpu().numpy())
                cls_id = int(boxes.cls[i].cpu().numpy())
                label = self._model.names[cls_id]
                
                detections.append(Detection(
                    label=label,
                    confidence=conf_score,
                    bbox=tuple(bbox)
                ))
        
        return DetectionResult(
            detections=detections,
            image_size=img_size
        )

    def detect_and_draw(
        self,
        image: Union[str, Path, Image.Image, np.ndarray],
        confidence: float = None,
        output_path: str = None,
    ) -> Tuple[DetectionResult, np.ndarray]:
        """
        检测并在图像上绘制结果
        
        Args:
            image: 图像输入
            confidence: 置信度阈值
            output_path: 输出路径（可选）
            
        Returns:
            (检测结果, 绘制后的图像)
        """
        self._load_model()
        
        conf = confidence if confidence is not None else self.confidence_threshold
        
        results = self._model(
            image,
            conf=conf,
            verbose=False
        )
        
        # 获取绘制后的图像
        annotated = results[0].plot()
        
        if output_path:
            Image.fromarray(annotated).save(output_path)
        
        # 解析检测结果
        result = self.detect(image, confidence)
        
        return result, annotated

    def unload(self):
        """卸载模型释放显存"""
        if self._model is not None:
            del self._model
            self._model = None
            self._loaded = False
            
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except:
                pass
            
            print("[Vision] 目标检测模型已卸载")

    def is_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._loaded
