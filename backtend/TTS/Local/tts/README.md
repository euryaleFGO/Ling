# TTS 模块说明

本目录为基于 MagicMirror 项目提取并重构的 CosyVoice2 TTS 语音合成核心模块，专注于音频生成功能。

**特点：**
- ✅ 仅保留音频生成功能，移除前端相关代码
- ✅ 适配 4GB 显卡，默认关闭 JIT 和 TRT 优化
- ✅ 复刻 MagicMirror 的核心设计思路（延迟初始化、音色缓存、并行处理等）

## 目录结构

```
tts/
├── cosyvoice/          # CosyVoice2 核心代码
│   ├── flow/          # Flow Matching 模块
│   ├── hifigan/       # HiFi-GAN 声码器
│   ├── llm/           # LLM 模块
│   ├── tokenizer/     # 分词器
│   ├── transformer/   # Transformer 编码器/解码器
│   └── utils/         # 工具函数
├── engine/            # TTS 引擎包装
│   ├── __init__.py    # 导出接口
│   └── tts_engine.py  # CosyvoiceRealTimeTTS 核心类
├── service.py         # 独立 HTTP 服务（可选）
└── README.md          # 本文件
```

## 核心特性

复刻自 MagicMirror/backend/TTS.py 的设计思路：

1. **延迟初始化**：避免在模块加载时初始化模型，支持按需初始化
2. **音色缓存**：首次生成时自动提取并缓存音色特征，后续生成无需重复提取
3. **并行处理**：使用线程池并行生成多个文本段，加速音频生成
4. **说话人管理**：支持零样本语音克隆和说话人信息保存
5. **显存优化**：统一清理显存，减少清理频率，适配4GB显卡
6. **文本切分**：智能切分长文本，按标点符号和最大长度切分
7. **音频处理**：支持单声道/立体声转换、归一化、淡入淡出等

## 使用方法

### 1. 基本使用

```python
from engine import CosyvoiceRealTimeTTS

# 初始化 TTS 引擎（4GB 显卡自动关闭 JIT/TRT）
model_path = "path/to/CosyVoice2-0.5B"
ref_audio = "path/to/reference_audio.wav"  # 可选，用于语音克隆
tts = CosyvoiceRealTimeTTS(model_path, ref_audio)  # JIT 和 TRT 默认已关闭

# 生成音频并返回 numpy 数组
result = tts.generate_audio("你好，这是一段测试文本")
if result:
    audio_data, sample_rate = result
    print(f"生成成功，时长 {len(audio_data) / sample_rate:.2f}s")
    
    # 保存为 WAV 文件
    tts.audio_to_wav_file(audio_data, sample_rate, "output.wav")
    
    # 或转换为字节流
    wav_bytes = tts.audio_to_wav_bytes(audio_data, sample_rate)
```

### 2. 使用已保存的说话人

```python
# 使用已保存的说话人 ID 生成音频
result = tts.generate_audio_with_speaker("你好", "spk_abc123")
```

### 3. 独立 HTTP 服务

```bash
# 启动独立 TTS 服务（默认端口 5001）
python service.py [model_path] [ref_audio_path]

# 或设置环境变量
export COSYVOICE_MODEL_PATH="path/to/model"
export COSYVOICE_REF_AUDIO="path/to/audio.wav"
export TTS_SERVICE_PORT=5001
python service.py
```

**API 接口：**

- `GET /health` - 健康检查
- `POST /tts/generate` - 生成音频
  ```json
  {
    "text": "要合成的文本",
    "spk_id": "speaker_id",  // 可选
    "use_clone": true         // 可选，是否使用语音克隆
  }
  ```
- `POST /tts/add_speaker` - 添加说话人
  - 表单字段：`audio` (文件), `prompt_text` (文本), `spk_id` (可选)
- `GET /tts/speakers` - 列出所有说话人
- `GET /audio/<filename>` - 获取音频文件

### 4. 文本转语音并保存文件

```python
# 直接生成并保存文件
tts.text_to_speech("你好，世界", output_file="output.wav")
```

## 配置说明

### 模型路径

- **模型路径**：CosyVoice2-0.5B 模型目录
- **参考音频**：用于零样本语音克隆的参考音频文件（WAV 格式，16kHz）

### 环境变量

- `COSYVOICE_MODEL_PATH`：默认模型路径
- `COSYVOICE_REF_AUDIO`：默认参考音频路径
- `TTS_SERVICE_PORT`：TTS 服务端口（默认 5001）
- `MODELSCOPE_CACHE`：ModelScope 缓存目录（默认 `~/.cache/modelscope`）

## 依赖要求

- Python 3.8+
- PyTorch
- NumPy
- Flask（仅 service.py 需要）
- Flask-CORS（仅 service.py 需要）

## 设计思路总结

### 从 MagicMirror 复刻的核心思路

1. **延迟初始化策略**
   - 不在 `__init__` 时加载模型，避免启动崩溃
   - 支持首次请求时初始化，提高容错性

2. **音色缓存机制**
   - 首次生成时提取 `prompt_semantic` 和 `spk_emb`
   - 后续生成复用缓存，避免重复计算
   - 使用锁保护缓存访问，保证线程安全

3. **并行处理优化**
   - 将长文本切分为多个段
   - 使用 `ThreadPoolExecutor` 并行生成
   - 用索引字典保持输出顺序

4. **显存管理**
   - 统一在最后清理显存，减少清理频率
   - 避免每个片段都清理，提高性能
   - 适配4GB显卡，默认关闭 JIT 和 TRT

5. **文本处理**
   - 按标点符号优先切分
   - 过滤纯标点/空白文本
   - 最大长度限制（120字符）

6. **音频处理**
   - 自动转换为单声道
   - 归一化到 [-1, 1]
   - 淡入淡出处理，避免爆音

7. **说话人管理**
   - 支持零样本语音克隆
   - 说话人信息持久化（spk2info.pt）
   - 支持多个说话人切换

## 与原 MagicMirror 的区别

1. **路径调整**：使用相对导入，适配当前项目结构
2. **模块化**：将引擎和服务分离，便于独立使用
3. **配置灵活**：支持环境变量和命令行参数
4. **简化接口**：专注于 TTS 核心功能，去除播放相关代码

## 注意事项

1. **显卡要求**：专门适配 4GB 显卡，强制关闭 JIT 和 TRT 优化（即使传入参数也会被忽略）
2. **内存管理**：长文本会自动切分，避免显存溢出
3. **线程安全**：音色缓存使用锁保护，支持多线程访问
4. **主线程初始化**：CosyVoice 必须在主线程中初始化，否则可能崩溃
5. **专注音频生成**：本模块专注于音频生成功能，不包含前端相关代码

## 开发提示

如需自定义或扩展，请直接在本目录下开发：

- 修改 `engine/tts_engine.py` 调整引擎行为
- 修改 `service.py` 调整 HTTP 服务接口
- 添加新的音频处理函数或说话人管理功能
