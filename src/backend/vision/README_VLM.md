# 视觉语言模型 (VLM) 使用指南

本文档介绍如何在玲 (Liying) 项目中使用 SmolVLM 等视觉语言模型。

---

## 📋 目录

- [模型介绍](#模型介绍)
- [模型下载](#模型下载)
- [目录结构](#目录结构)
- [使用方法](#使用方法)
- [配置说明](#配置说明)
- [示例代码](#示例代码)

---

## 🤖 模型介绍

### SmolVLM-256M

**SmolVLM-256M** 是一个轻量级的视觉语言模型，具有以下特点：

- **参数量**: 256M（非常轻量）
- **功能**: 图像理解、视觉问答、图像描述
- **优势**: 
  - 模型小，加载快
  - 推理速度快
  - 显存占用低（~1GB）
  - 支持中英文
- **适用场景**: 
  - 图像描述生成
  - 视觉问答
  - 图像内容理解
  - 多轮视觉对话

### 其他支持的模型

- **SmolVLM-500M**: 更大的版本，性能更好
- **其他 HuggingFace VLM 模型**: 只要兼容 `AutoModelForVision2Seq` 接口

---

## 📥 模型下载

### 方式 1: 从 HuggingFace 下载

```bash
# 使用 huggingface-cli
huggingface-cli download HuggingFaceTB/SmolVLM-256M-Instruct \
    --local-dir E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M

# 或使用 Python
from huggingface_hub import snapshot_download
snapshot_download(
    "HuggingFaceTB/SmolVLM-256M-Instruct",
    local_dir="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M"
)
```

### 方式 2: 手动下载

1. 访问 [HuggingFace 模型页面](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct)
2. 下载所有文件到本地目录
3. 放置到 `models/Vision/VLM/SmolVLM-256M/` 目录

---

## 📁 目录结构

推荐的模型目录结构：

```
E:/Avalon/Chaldea/Liying/models/Vision/
├── VLM/                          # 视觉语言模型
│   ├── SmolVLM-256M/            # SmolVLM-256M 模型
│   │   ├── config.json
│   │   ├── model.safetensors
│   │   ├── preprocessor_config.json
│   │   ├── processor_config.json
│   │   └── ...
│   └── SmolVLM-500M/            # SmolVLM-500M 模型（可选）
│
├── OCR/                          # OCR 模型
│   ├── easyocr/                 # EasyOCR 模型
│   └── paddleocr/               # PaddleOCR 模型（可选）
│
├── YOLO/                         # YOLO 目标检测模型
│   ├── yolov8n.pt               # YOLOv8 nano
│   ├── yolov8s.pt               # YOLOv8 small
│   └── yolov8m.pt               # YOLOv8 medium
│
└── Captioner/                    # 图像描述模型
    └── blip-image-captioning-base/
```

---

## 🚀 使用方法

### 方式 1: 直接使用 VLM 模块

```python
from backend.vision.models.vlm import VLMModel

# 初始化模型
vlm = VLMModel(
    model_path="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M",
    device="cuda",  # 或 "cpu"
    use_fp16=True
)

# 生成图像描述
result = vlm.generate(
    image="image.jpg",
    prompt="请详细描述这张图片的内容"
)
print(result.text)

# 回答问题
result = vlm.generate(
    image="image.jpg",
    prompt="图片中有几个人？"
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
print(result.text)

# 卸载模型
vlm.unload()
```

### 方式 2: 通过视觉引擎使用

```python
from backend.vision import VisionEngine, VisionConfig

# 配置启用 VLM
config = VisionConfig(
    enable_vlm=True,
    vlm_model="SmolVLM-256M",
    vlm_model_path="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M",
    device="cuda"
)

# 初始化引擎
vision = VisionEngine(config)

# 使用 VLM 分析图像
response = vision.vlm_analyze(
    image="image.jpg",
    prompt="请详细描述这张图片"
)
print(response)

# 多轮对话
response = vision.vlm_chat(
    image="image.jpg",
    messages=[
        {"role": "user", "content": "图片中有什么？"},
        {"role": "assistant", "content": "有一只猫"},
        {"role": "user", "content": "猫在做什么？"}
    ]
)
print(response)
```

### 方式 3: 结合其他视觉模块

```python
from backend.vision import VisionEngine, VisionConfig, VisionModule

# 配置多个模块
config = VisionConfig(
    enable_vlm=True,
    enable_ocr=True,
    enable_detector=True,
    vlm_model_path="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M"
)

vision = VisionEngine(config)

# 综合分析（使用所有模块）
result = vision.analyze("image.jpg")
print(result.to_context())

# 输出示例:
# [图像分析结果]
# 🤖 VLM 分析: 这是一张在咖啡厅拍摄的照片，一位女士坐在桌前，桌上有一杯咖啡...
# 🔍 检测物体: 人, 杯子, 椅子, 桌子
# 📖 图中文字: STARBUCKS

# 仅使用 VLM
result = vision.analyze("image.jpg", modules=[VisionModule.VLM])
print(result.vlm_response)
```

---

## ⚙️ 配置说明

### VisionConfig 参数

```python
from backend.vision import VisionConfig

config = VisionConfig(
    # VLM 开关
    enable_vlm=True,                    # 是否启用 VLM
    
    # VLM 模型配置
    vlm_model="SmolVLM-256M",          # 模型名称
    vlm_model_path="path/to/model",    # 模型路径（None 使用默认路径）
    
    # 设备配置
    device="auto",                      # "auto", "cpu", "cuda", "cuda:0"
    use_fp16=True,                      # 是否使用半精度（FP16）
    
    # 其他模块
    enable_captioner=True,              # 图像描述
    enable_detector=True,               # 目标检测
    enable_ocr=True,                    # OCR
)
```

### 环境变量配置

在 `.env` 文件中配置默认路径：

```bash
# 模型根目录
LIYING_MODELS_DIR=E:/Avalon/Chaldea/Liying/models

# VLM 模型路径（可选，不设置则使用默认路径）
LIYING_VLM_MODEL_PATH=E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M
```

---

## 📝 示例代码

### 示例 1: 图像描述

```python
from backend.vision.models.vlm import VLMModel

vlm = VLMModel(
    model_path="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M"
)

# 中文描述
desc_zh = vlm.describe_image("photo.jpg", language="zh")
print(f"中文: {desc_zh}")

# 英文描述
desc_en = vlm.describe_image("photo.jpg", language="en")
print(f"English: {desc_en}")
```

### 示例 2: 视觉问答

```python
from backend.vision.models.vlm import VLMModel

vlm = VLMModel(
    model_path="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M"
)

# 回答问题
questions = [
    "图片中有几个人？",
    "他们在做什么？",
    "背景是什么地方？",
    "图片的整体氛围如何？"
]

for q in questions:
    answer = vlm.answer_question("photo.jpg", q)
    print(f"Q: {q}")
    print(f"A: {answer}\n")
```

### 示例 3: 多轮对话

```python
from backend.vision.models.vlm import VLMModel

vlm = VLMModel(
    model_path="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M"
)

# 对话历史
conversation = []

# 第一轮
conversation.append({"role": "user", "content": "这张图片里有什么？"})
result = vlm.chat("photo.jpg", conversation)
conversation.append({"role": "assistant", "content": result.text})
print(f"AI: {result.text}\n")

# 第二轮
conversation.append({"role": "user", "content": "能详细描述一下主要物体吗？"})
result = vlm.chat("photo.jpg", conversation)
conversation.append({"role": "assistant", "content": result.text})
print(f"AI: {result.text}\n")

# 第三轮
conversation.append({"role": "user", "content": "这张照片可能是在什么时候拍的？"})
result = vlm.chat("photo.jpg", conversation)
print(f"AI: {result.text}\n")
```

### 示例 4: 集成到 Agent

```python
from backend.llm.agent import Agent
from backend.vision import VisionEngine, VisionConfig

# 配置视觉引擎
vision_config = VisionConfig(
    enable_vlm=True,
    vlm_model_path="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M"
)
vision = VisionEngine(vision_config)

# 初始化 Agent
agent = Agent(user_id="default_user")

# 分析图像
image_path = "screenshot.png"
vision_context = vision.analyze_for_llm(image_path, style="detailed")

# 将视觉上下文传给 Agent
response = agent.chat(f"请根据以下图像分析结果回答问题：\n\n{vision_context}\n\n问题：图片中的人在做什么？")
print(response)
```

---

## 🎯 最佳实践

### 1. 模型选择

- **SmolVLM-256M**: 适合快速推理，显存占用低
- **SmolVLM-500M**: 性能更好，但显存占用更高

### 2. 设备选择

```python
# 自动选择（推荐）
config = VisionConfig(device="auto")

# 强制使用 GPU
config = VisionConfig(device="cuda")

# 强制使用 CPU（慢但兼容性好）
config = VisionConfig(device="cpu")

# 指定 GPU
config = VisionConfig(device="cuda:0")
```

### 3. 内存管理

```python
# 使用完后及时卸载
vlm = VLMModel(model_path="...")
result = vlm.generate(image, prompt)
vlm.unload()  # 释放显存

# 或使用上下文管理器（待实现）
```

### 4. 批量处理

```python
vlm = VLMModel(model_path="...")

images = ["img1.jpg", "img2.jpg", "img3.jpg"]
results = []

for img in images:
    result = vlm.generate(img, "描述这张图片")
    results.append(result.text)

vlm.unload()
```

---

## ❓ 常见问题

### Q1: 模型加载失败

**问题**: `FileNotFoundError` 或模型加载错误

**解决**:
1. 检查模型路径是否正确
2. 确认模型文件完整（包含 config.json, model.safetensors 等）
3. 检查 transformers 版本：`pip install transformers>=4.30.0`

### Q2: 显存不足

**问题**: `CUDA out of memory`

**解决**:
1. 使用更小的模型（SmolVLM-256M）
2. 启用 FP16：`use_fp16=True`
3. 使用 CPU：`device="cpu"`
4. 减少 `max_new_tokens`

### Q3: 生成速度慢

**问题**: 推理速度慢

**解决**:
1. 使用 GPU 而不是 CPU
2. 启用 FP16
3. 减少 `max_new_tokens`
4. 使用更小的模型

### Q4: 中文输出乱码

**问题**: 生成的中文文本乱码

**解决**:
1. 确保使用支持中文的模型
2. 检查 prompt 是否使用中文
3. 更新 transformers 库

---

## 📚 参考资料

- [SmolVLM 官方文档](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct)
- [Transformers 文档](https://huggingface.co/docs/transformers)
- [视觉引擎文档](README.md)

---

**祝你使用愉快！** 🎉
