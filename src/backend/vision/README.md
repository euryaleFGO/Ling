# 视觉理解模块

轻量级图像理解模块，整合图像描述、目标检测、文字识别功能，输出结构化上下文给 LLM。

## 功能特性

- **图像描述 (BLIP)**: 生成自然语言图像描述
- **目标检测 (YOLOv8)**: 检测图像中的物体
- **文字识别 (EasyOCR)**: 识别图像中的中英文文字
- **统一接口**: 一键分析，输出 LLM 可用的上下文

## 资源占用

| 模块 | 模型 | 显存/内存 | 加载时间 |
|------|------|----------|----------|
| 图像描述 | BLIP-base | ~1.5GB (GPU) / ~2GB (CPU) | ~10s |
| 目标检测 | YOLOv8n | ~200MB | ~2s |
| 文字识别 | EasyOCR | ~1GB | ~5s |

**提示**: 各模块延迟加载，只有使用时才会占用资源。

## 依赖安装

```bash
# 核心依赖
pip install pillow numpy

# 图像描述 (BLIP)
pip install transformers torch torchvision

# 目标检测 (YOLO)
pip install ultralytics

# 文字识别 (OCR)
pip install easyocr
# 或使用 PaddleOCR（需要先安装 PaddlePaddle）
# pip install paddlepaddle paddleocr
```

## 快速开始

### 1. 基本使用

```python
from backend.vision import VisionEngine

# 初始化引擎
vision = VisionEngine()

# 分析图片
result = vision.analyze("image.jpg")

# 获取 LLM 上下文
print(result.to_context())
```

输出示例:
```
[图像分析结果]
📝 图像描述: a woman sitting at a cafe with a cup of coffee
🔍 检测物体: 人, 杯子, 椅子, 桌子
📖 图中文字: STARBUCKS | WiFi: guest
```

### 2. 自定义配置

```python
from backend.vision import VisionEngine, VisionConfig

config = VisionConfig(
    # 模块开关
    enable_captioner=True,
    enable_detector=True,
    enable_ocr=True,
    
    # 模型选择
    captioner_model="Salesforce/blip-image-captioning-base",
    detector_model="yolov8n",  # 最轻量版本
    ocr_backend="easyocr",
    
    # 设备配置
    device="auto",  # 自动选择 GPU/CPU
    use_fp16=True,  # 半精度节省显存
    
    # 检测阈值
    detection_confidence=0.5,
    ocr_confidence=0.5,
)

vision = VisionEngine(config)
```

### 3. 单独使用各模块

```python
# 只生成描述
caption = vision.caption("image.jpg")

# 只检测物体
objects = vision.detect("image.jpg")

# 只识别文字
text = vision.ocr("image.jpg")
```

### 4. 释放资源

```python
# 卸载所有模块
vision.unload()

# 或只卸载特定模块
from backend.vision.vision_engine import VisionModule
vision.unload([VisionModule.CAPTIONER])
```

## 与 Agent 集成

视觉模块可以作为 Agent 的 Tool 使用：

```python
# 在 Agent 中调用
def handle_image(image_path: str, user_question: str) -> str:
    # 分析图像
    context = vision.analyze_for_llm(image_path)
    
    # 构建 prompt
    prompt = f"{context}\n\n用户问题: {user_question}"
    
    # 调用 LLM
    return llm.chat(prompt)
```

## API 参考

### VisionEngine

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `analyze(image)` | 完整分析图像 | `VisionResult` |
| `analyze_for_llm(image)` | 分析并返回上下文字符串 | `str` |
| `caption(image)` | 只生成描述 | `str` |
| `detect(image)` | 只检测物体 | `List[str]` |
| `ocr(image)` | 只识别文字 | `str` |
| `unload(modules)` | 卸载模块释放资源 | `None` |

### VisionConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_captioner` | bool | True | 启用图像描述 |
| `enable_detector` | bool | True | 启用目标检测 |
| `enable_ocr` | bool | True | 启用 OCR |
| `captioner_model` | str | blip-base | BLIP 模型 |
| `detector_model` | str | yolov8n | YOLO 模型 |
| `ocr_backend` | str | easyocr | OCR 后端 |
| `device` | str | auto | 设备选择 |
| `use_fp16` | bool | True | 半精度 |

### VisionResult

| 属性/方法 | 说明 |
|----------|------|
| `caption` | 图像描述 |
| `objects` | 检测到的物体列表 |
| `ocr_text` | OCR 识别的文字 |
| `to_context(style)` | 转换为 LLM 上下文 |

## 性能优化建议

1. **显存不足时**:
   - 设置 `enable_captioner=False`（最耗显存）
   - 使用 `device="cpu"` 强制 CPU
   - 设置 `use_fp16=True`

2. **只需要特定功能**:
   - 只启用需要的模块
   - 用完后调用 `unload()`

3. **批量处理**:
   - 保持 Engine 实例复用
   - 避免反复加载/卸载模型

## 常见问题

**Q: 第一次运行很慢？**
A: 首次运行会下载模型到缓存，之后会快很多。

**Q: 显存不够用？**
A: 禁用图像描述模块（最耗显存），或使用 CPU 模式。

**Q: OCR 中文识别不准？**
A: 确保 `ocr_languages=["ch_sim", "en"]` 包含中文。

**Q: 如何使用本地模型？**
A: 将 `captioner_model` 设为本地路径即可。
