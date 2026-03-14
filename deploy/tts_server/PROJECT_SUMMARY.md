# TTS 服务器项目总结报告

**生成日期**：2026-02-27  
**项目路径**：`/root/autodl-tmp/tts_server`

---

## 一、项目概述

本项目是基于 **CosyVoice2-0.5B** 的独立 TTS（文本转语音）云端服务，提供 HTTP API，支持：

- **同步生成**：一次性返回完整音频
- **流式生成**：按句/段边合成边返回（SSE）
- **队列模式**：异步入队 + 拉取（`/tts/enqueue` + `/tts/dequeue`）
- **说话人注册**：预注册音色，生成时直接按 `spk_id` 调用
- **三秒克隆**：使用参考音频实时克隆音色
- **唇形同步**：Rhubarb Lip Sync 视觉素分析（可选）

---

## 二、技术栈

| 组件 | 说明 |
|------|------|
| **TTS 引擎** | CosyVoice2-0.5B（阿里开源） |
| **Web 框架** | Flask |
| **推理加速** | TensorRT（可选，需预先导出 .plan） |
| **唇形分析** | Rhubarb Lip Sync |
| **依赖** | PyTorch、ONNX Runtime、modelscope 等 |

---

## 三、目录结构

```
tts_server/
├── service.py              # 主服务入口（Flask）
├── client_example.py       # 本地调用示例
├── start.sh                # 启动脚本
├── requirements.txt        # Python 依赖
├── README.md               # 部署与 API 说明
├── rhubarb                 # Rhubarb Lip Sync 可执行文件
├── engine/                 # TTS 引擎封装
│   ├── tts_engine.py       # CosyVoice 实时 TTS
│   └── edge_tts_engine.py
├── cosyvoice/              # CosyVoice2 核心代码
├── third_party/            # Matcha-TTS 等第三方
├── res/                    # Sphinx 声学模型等资源
├── reference_audio/        # 参考音频（用于克隆/注册）
│   ├── zjj.wav             # 默认参考音频
│   ├── Ling.wav            # 玲 说话人参考音频
│   └── Ling.mp3            # 原始格式
├── models/TTS/CosyVoice2-0.5B/
│   ├── spk2info.pt         # 说话人注册信息（玲 等）
│   ├── configuration.json  # 模型配置
│   ├── cosyvoice2.yaml     # 结构与训练配置
│   ├── CosyVoice-BlankEN/  # 英文分词器
│   └── *.pt, *.onnx, *.plan # 模型权重（需单独下载）
└── audio_output/           # 生成的 WAV 输出目录
```

---

## 四、API 接口一览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/tts/generate` | POST | 同步生成音频 |
| `/tts/generate/stream` | POST | 流式生成（SSE） |
| `/tts/enqueue` | POST | 异步入队 |
| `/tts/dequeue` | GET | 拉取音频段 |
| `/tts/speakers` | GET | 列出已注册说话人 |
| `/tts/add_speaker` | POST | 添加说话人（上传音频 + 文本） |

---

## 五、生成模式说明

| 模式 | 触发条件 | 参考来源 | 特点 |
|------|----------|----------|------|
| **说话人注册** | 请求带 `spk_id`（如 `"玲"`） | `spk2info.pt` 中预注册 embedding | 速度快，无需参考音频 |
| **三秒克隆** | 无 `spk_id`，`use_clone=True` | 启动时加载的 `DEFAULT_REF_AUDIO`（默认 `zjj.wav`） | 每次用参考音频实时克隆 |

**重要**：调用方若要用「玲」的音色，必须在请求中传 `"spk_id": "玲"`，否则会走三秒克隆，使用默认参考音频（zjj.wav）。

---

## 六、已注册说话人

| 说话人 ID | 参考音频 | 参考文本 |
|-----------|----------|----------|
| 玲 | Ling.wav | 永远相信美好的事情即将发生 |

---

## 七、配置与环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `COSYVOICE_MODEL_PATH` | 模型目录 | `models/TTS/CosyVoice2-0.5B` |
| `COSYVOICE_REF_AUDIO` | 默认参考音频（三秒克隆用） | `reference_audio/zjj.wav` |
| `COSYVOICE_USE_TRT` | 是否启用 TensorRT | `auto`（有 .plan 则启用） |
| `TTS_QUEUE_MAX_WORKERS` | 队列模式并行数 | 2 |

---

## 八、打包说明（当前压缩包）

本压缩包**不包含模型权重**（约 5GB），仅保留：

- 全部源码与配置
- `reference_audio/` 下所有参考音频
- `models/TTS/CosyVoice2-0.5B/spk2info.pt`（说话人注册）
- 模型目录下的配置文件与分词器（`configuration.json`、`cosyvoice2.yaml`、`CosyVoice-BlankEN/` 等）

**恢复使用**：需从 ModelScope 下载完整模型到 `models/TTS/CosyVoice2-0.5B/`：

```bash
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('iic/CosyVoice2-0.5B', local_dir='models/TTS/CosyVoice2-0.5B')"
```

下载后会覆盖部分文件，但会保留本包中的 `spk2info.pt`（若 ModelScope 包内无此文件）。若被覆盖，需重新注册说话人。

---

## 九、快速启动

```bash
cd tts_server
pip install -r requirements.txt
# 安装 PyTorch、下载模型（见上）
python service.py --host 0.0.0.0 --port 5001
```

---

*报告结束*
