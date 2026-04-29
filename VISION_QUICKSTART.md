# 视觉模块快速开始

**5 分钟快速使用 SmolVLM 和其他视觉模型**

---

## 📁 第一步：准备模型目录

创建以下目录结构：

```
E:/Avalon/Chaldea/Liying/models/Vision/
├── VLM/
│   └── SmolVLM-256M/        # 放置 SmolVLM 模型
├── OCR/
│   └── easyocr/             # EasyOCR 自动下载
├── YOLO/
│   └── yolov8n.pt           # YOLO 模型
└── Captioner/
    └── blip-image-captioning-base/  # BLIP 模型
```

---

## 📥 第二步：下载 SmolVLM 模型

### 方式 1: 使用 Python

```python
from huggingface_hub import snapshot_download

snapshot_download(
    "HuggingFaceTB/SmolVLM-256M-Instruct",
    local_dir="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M"
)
```

### 方式 2: 使用命令行

```bash
huggingface-cli download HuggingFaceTB/SmolVLM-256M-Instruct \
    --local-dir E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M
```

---

## 🚀 第三步：使用 VLM

### 方式 1: 直接使用

```python
from backend.vision.models.vlm import VLMModel

# 初始化
vlm = VLMModel(
    model_path="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M"
)

# 分析图像
result = vlm.generate("image.jpg", "描述这张图片")
print(result.text)

# 卸载
vlm.unload()
```

### 方式 2: 通过视觉引擎

```python
from backend.vision import VisionEngine, VisionConfig

# 配置
config = VisionConfig(
    enable_vlm=True,
    vlm_model_path="E:/Avalon/Chaldea/Liying/models/Vision/VLM/SmolVLM-256M"
)

# 使用
vision = VisionEngine(config)
response = vision.vlm_analyze("image.jpg", "描述这张图片")
print(response)
```

---

## 🧪 第四步：测试

```bash
# 基本测试
python scripts/test_vlm.py --image image.jpg

# 问答模式
python scripts/test_vlm.py --image image.jpg --qa

# 对话模式
python scripts/test_vlm.py --image image.jpg --chat
```

---

## 📖 更多信息

- [完整文档](src/backend/vision/README_VLM.md)
- [集成报告](docs/VLM_INTEGRATION_COMPLETE.md)

---

**就这么简单！** 🎉
