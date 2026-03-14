# ASR 模块 - 语音识别

基于 FunASR 精简版的流式语音识别模块。

## 功能特性

- **流式识别**: 支持实时语音转文字，低延迟
- **中文优化**: 使用阿里达摩院 Paraformer 模型，中文识别精度高
- **VAD 支持**: 自动检测语音活动，过滤静音
- **GPU 加速**: 支持 ONNX Runtime GPU 推理

## 模型下载

请手动下载以下模型到 `E:\Avalon\Chaldea\Liying\models\ASR\` 目录：

### 必需模型

```bash
cd E:\Avalon\Chaldea\Liying\models
mkdir ASR
cd ASR

# 安装 git-lfs（如果没有）
git lfs install

# 下载流式 ASR 模型 (~880MB)
git clone https://huggingface.co/funasr/paraformer-zh-streaming

# 下载 VAD 模型 (~1.6MB)
git clone https://huggingface.co/funasr/fsmn-vad
```

### 下载完成后的目录结构

```
models/ASR/
├── paraformer-zh-streaming/
│   ├── model.onnx          # 编码器模型
│   ├── decoder.onnx        # 解码器模型
│   ├── config.yaml         # 配置文件
│   ├── am.mvn              # CMVN 归一化参数
│   └── tokens.json         # Token 列表
└── fsmn-vad/
    ├── model.onnx          # VAD 模型
    ├── config.yaml         # 配置文件
    └── am.mvn              # CMVN 归一化参数
```

## 依赖安装

```bash
pip install onnxruntime        # CPU 推理
# 或
pip install onnxruntime-gpu    # GPU 推理

pip install librosa            # 音频处理
pip install kaldi-native-fbank # Fbank 特征提取
pip install pyyaml             # 配置文件解析
pip install sounddevice        # 麦克风输入（可选）
```

## 使用方法

### 1. 离线识别（识别整个音频文件）

```python
from backend.asr import ASREngine

# 初始化引擎
asr = ASREngine(model_dir="models/ASR/paraformer-zh-streaming")

# 识别文件
text = asr.recognize_file("audio.wav")
print(text)
```

### 2. 流式识别（实时处理音频流）

```python
from backend.asr import ASREngine

asr = ASREngine(model_dir="models/ASR/paraformer-zh-streaming")

# 开始流式识别
asr.start_stream()

# 输入音频块（每块约 600ms）
for chunk in audio_chunks:
    text = asr.feed_audio(chunk)
    if text:
        print(text, end="", flush=True)

# 结束识别
final_text = asr.end_stream()
print(final_text)
```

### 3. 麦克风实时识别

```python
from backend.asr import ASREngine

asr = ASREngine(model_dir="models/ASR/paraformer-zh-streaming")

def on_result(text, is_final):
    print(text, end="" if not is_final else "\n")

# 开始麦克风识别
asr.start_microphone(callback=on_result)

# 按 Ctrl+C 停止
input("按 Enter 停止...")
asr.stop_microphone()
```

### 4. 使用配置对象

```python
from backend.asr import ASREngine, ASRConfig

config = ASRConfig(
    model_dir="models/ASR/paraformer-zh-streaming",
    vad_dir="models/ASR/fsmn-vad",
    device_id="0",        # 使用 GPU
    quantize=True,        # 使用量化模型（更快但精度略低）
    chunk_size=[5, 10, 5], # 流式块配置
    sample_rate=16000,
)

asr = ASREngine(config=config)
```

## 流式配置说明

`chunk_size` 参数控制流式识别的延迟和精度：

- `[5, 10, 5]` (默认): 延迟 ~600ms，精度高
- `[0, 10, 5]`: 延迟 ~600ms，无左上下文
- `[0, 8, 4]`: 延迟 ~480ms，速度快但精度略低

计算公式:
- 每块输入: `chunk_size[1] * 60ms` 的音频
- 延迟: `(chunk_size[0] + chunk_size[2]) * 60ms`

## API 参考

### ASREngine

| 方法 | 说明 |
|------|------|
| `recognize_file(path)` | 识别音频文件 |
| `recognize_audio(audio, sr)` | 识别音频数据 |
| `start_stream()` | 开始流式识别 |
| `feed_audio(chunk)` | 输入音频块 |
| `end_stream()` | 结束流式识别 |
| `start_microphone(callback)` | 开始麦克风识别 |
| `stop_microphone()` | 停止麦克风识别 |

### ASRConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model_dir` | str | None | ASR 模型目录 |
| `vad_dir` | str | None | VAD 模型目录 |
| `device_id` | str | "-1" | 设备ID，"-1"=CPU |
| `quantize` | bool | False | 使用量化模型 |
| `chunk_size` | List[int] | [5,10,5] | 流式块配置 |
| `sample_rate` | int | 16000 | 采样率 |
| `use_vad` | bool | True | 是否使用 VAD |

## 注意事项

1. **模型格式**: 模型必须是 ONNX 格式。如果下载的是 PyTorch 格式，需要先导出为 ONNX。

2. **音频格式**: 输入音频应为 16kHz 单声道。其他格式会自动重采样。

3. **GPU 推理**: 需要安装 `onnxruntime-gpu` 并设置 `device_id="0"`。

4. **内存占用**: 流式识别会保持缓存，长时间使用建议定期调用 `start_stream()` 重置。

## 致谢

本模块基于 [FunASR](https://github.com/modelscope/FunASR) 项目精简而来，感谢阿里达摩院的开源贡献。
