# 玲  - 智能虚拟助手

> 一个集成大语言模型、Live2D 虚拟形象、语音合成于一体的智能虚拟助手系统

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Java](https://img.shields.io/badge/Java-17-orange.svg)](https://www.java.com/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.3.1-green.svg)](https://pytorch.org/)
[![CUDA](https://img.shields.io/badge/CUDA-12.4-76B900.svg)](https://developer.nvidia.com/cuda-toolkit)

## 📋 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [详细配置](#详细配置)
- [使用指南](#使用指南)
- [开发说明](#开发说明)
- [常见问题](#常见问题)
- [性能优化](#性能优化)
- [路线图](#路线图)

---

## 🎯 项目简介

**玲 (Liying)** 是一个智能虚拟助手系统，整合了以下核心功能：

- 🤖 **大语言模型 (LLM)**：基于 DeepSeek API 的智能对话，支持工具调用和记忆管理
- 🎭 **Live2D 虚拟形象**：基于 Live2D Cubism SDK 的桌面宠物，实时显示对话内容
- 🎤 **语音合成 (TTS)**：基于 CosyVoice2 的零样本语音克隆，将文本转换为自然语音
- 💾 **持久化存储**：基于 MongoDB 和 ChromaDB 的对话记忆和向量检索

系统通过模块化设计实现了 LLM、Live2D、TTS 的有机整合，为用户提供沉浸式的智能交互体验。

---

## ✨ 核心特性

### 1. 智能对话系统
- ✅ **支持工具调用**：Agent 可自主决定调用工具（搜索、记忆、截图等）
- ✅ **多轮对话**：基于 RAG 的上下文检索，支持长期记忆管理
- ✅ **流式响应**：实时返回生成内容，提升用户体验
- ✅ **记忆提取**：自动提取并存储重要信息到长期记忆

### 2. Live2D 虚拟形象
- ✅ **桌面宠物**：透明的桌面宠物窗口，不遮挡其他应用
- ✅ **实时对话显示**：AI 回复自动显示在语音气泡中
- ✅ **流畅动画**：基于 OpenGL 的高性能渲染
- ✅ **跨平台**：支持 Windows、Linux、macOS

### 3. 语音合成 (TTS)
- ✅ **零样本语音克隆**：基于参考音频实现语音克隆
- ✅ **并行处理**：多线程并行生成，加速音频合成
- ✅ **显存优化**：适配 4GB 显卡，自动关闭 JIT/TRT 优化
- ✅ **音色缓存**：首次提取后缓存音色特征，后续快速生成

### 4. 系统集成
- ✅ **模块化设计**：各模块独立运行，易于维护和扩展
- ✅ **消息队列**：基于 HTTP 的消息传递，解耦各模块
- ✅ **自动启动**：一键启动所有服务，包括 MongoDB 和 Live2D
- ✅ **错误恢复**：完善的错误处理和日志记录

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户交互层                             │
│  ┌──────────────┐      ┌──────────────┐                     │
│  │  Live2D 窗口 │      │  命令行输入  │                     │
│  │   (Java)     │      │  (Python)    │                     │
│  └──────┬───────┘      └──────┬───────┘                     │
└─────────┼──────────────────────┼─────────────────────────────┘
          │                      │
          │ HTTP (轮询)          │ HTTP (POST)
          │                      │
┌─────────▼──────────────────────▼─────────────────────────────┐
│                   消息服务器 (Message Server)                  │
│                   端口: 8765                                   │
│              Python http.server                               │
└─────────┬──────────────────────┬─────────────────────────────┘
          │                      │
          │                      │
┌─────────▼──────────────────────▼─────────────────────────────┐
│                     应用核心层                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              LLM 模块 (backtend/LLM/)                │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │  │  Agent   │  │  Memory  │  │  Tools   │          │   │
│  │  │  智能代理 │  │ 记忆管理  │  │ 工具调用  │          │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘          │   │
│  │       └─────────────┼──────────────┘                │   │
│  │                     │                               │   │
│  │              ┌──────▼──────┐                        │   │
│  │              │  DeepSeek   │                        │   │
│  │              │     API     │                        │   │
│  │              └─────────────┘                        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          TTS 模块 (backtend/TTS/Local/tts/)          │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │  │ CosyVoice│  │  Engine  │  │  音频    │          │   │
│  │  │   模型   │  │  引擎    │  │  生成    │          │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘          │   │
│  │       └─────────────┼──────────────┘                │   │
│  │                     │                               │   │
│  │              ┌──────▼──────┐                        │   │
│  │              │   NVIDIA    │                        │   │
│  │              │     GPU     │                        │   │
│  │              └─────────────┘                        │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────┬──────────────────────┬─────────────────────────────┘
          │                      │
          │                      │
┌─────────▼──────────────────────▼─────────────────────────────┐
│                     数据存储层                                 │
│  ┌──────────────┐      ┌──────────────┐                     │
│  │   MongoDB    │      │   ChromaDB   │                     │
│  │  对话历史    │      │  向量检索    │                     │
│  └──────────────┘      └──────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

### 消息流程

1. **用户输入** → `send_user_message.py` 发送消息到 `message_server.py`
2. **LLM 处理** → `Agent` 调用 DeepSeek API 生成回复
3. **消息传递** → AI 回复通过 `message_server.py` 发送到队列
4. **Live2D 显示** → Java 端轮询获取消息，显示在语音气泡中
5. **语音生成** → 同时调用 TTS 引擎生成语音文件

---

## 🛠️ 技术栈

### 后端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.12 | 主要开发语言 |
| PyTorch | 2.3.1 | TTS 模型推理 |
| CUDA | 12.4 | GPU 加速 |
| MongoDB | Latest | 对话历史存储 |
| ChromaDB | Latest | 向量数据库 |
| DeepSeek API | - | 大语言模型 |

### 前端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| Java | 17 | Live2D 渲染 |
| Live2D Cubism SDK | 4.0+ | 虚拟形象 |
| LWJGL | 3.3.3 | OpenGL 渲染 |
| Maven | 3.8+ | 构建工具 |

### 核心依赖

#### LLM 模块
- `openai` - API 调用
- `pymongo` - MongoDB 连接
- `chromadb` - 向量数据库
- `transformers` - 文本处理

#### TTS 模块
- `torch` - PyTorch 深度学习框架
- `librosa` - 音频处理
- `soundfile` - 音频文件 I/O
- `onnxruntime` - ONNX 模型推理
- `modelscope` - 模型下载

#### 其他
- `PyQt6` - GUI 界面
- `requests` - HTTP 请求
- `numpy` - 数值计算

---

## 📁 项目结构

```
Liying/
├── backtend/                      # 后端代码
│   ├── LLM/                       # 大语言模型模块
│   │   ├── agent/                 # 智能代理
│   │   │   ├── agent.py           # Agent 核心类
│   │   │   └── tool_manager.py    # 工具管理
│   │   ├── api_infer/             # API 推理
│   │   │   ├── openai_infer.py    # OpenAI 兼容 API
│   │   │   └── config.py          # 配置文件
│   │   ├── memory/                # 记忆管理
│   │   │   ├── context_manager.py # 上下文管理
│   │   │   ├── long_term_memory.py # 长期记忆
│   │   │   └── memory_extractor.py # 记忆提取
│   │   ├── database/              # 数据库
│   │   │   ├── mongo_client.py    # MongoDB 客户端
│   │   │   ├── chroma_client.py   # ChromaDB 客户端
│   │   │   └── knowledge_dao.py   # 知识库 DAO
│   │   └── tools/                 # 工具集合
│   │       ├── search_tool.py     # 搜索工具
│   │       ├── memory_tool.py     # 记忆工具
│   │       └── ...
│   │
│   ├── TTS/                       # 语音合成模块
│   │   └── Local/                 # 本地 TTS
│   │       └── tts/               # TTS 核心代码
│   │           ├── cosyvoice/     # CosyVoice2 模型
│   │           ├── engine/        # TTS 引擎
│   │           │   └── tts_engine.py
│   │           └── service.py     # TTS HTTP 服务
│   │
│   └── models/                    # 模型文件
│       ├── embedding/             # 嵌入模型
│       └── TTS/                   # TTS 模型
│           └── CosyVoice2-0.5B/
│
├── frontend/                      # 前端代码
│   └── Live2DPet/                 # Live2D 桌面宠物
│       ├── src/main/java/         # Java 源码
│       │   └── com/live2d/        # 核心类
│       │       ├── Main.java      # 主程序
│       │       ├── Live2DModel.java # 模型管理
│       │       └── SpeechBubble.java # 语音气泡
│       ├── pom.xml                # Maven 配置
│       └── README.md              # 说明文档
│
├── gui/                           # GUI 界面（可选）
│   └── main_window.py             # 主窗口
│
├── launcher.py                    # 启动器（MongoDB + Live2D）
├── message_server.py              # 消息服务器
├── send_user_message.py           # 用户消息发送脚本
├── test_tts.py                    # TTS 测试脚本
│
├── install_tts_dependencies.bat   # TTS 依赖安装脚本
├── install_tts_requirements.txt   # TTS 依赖列表
└── README.md                      # 本文档
```

---

## 🚀 快速开始

### 环境要求

- **操作系统**: Windows 10/11 (推荐), Linux, macOS
- **Python**: 3.12+
- **Java**: 17+
- **CUDA**: 12.1+ (可选，用于 GPU 加速)
- **显卡**: NVIDIA GPU，4GB+ 显存 (推荐)
- **内存**: 8GB+ RAM
- **磁盘**: 10GB+ 可用空间

### 1. 克隆项目

```bash
git clone <repository-url>
cd Liying
```

### 2. 创建 Python 环境

```bash
# 使用 conda (推荐)
conda create -n Liying python=3.12
conda activate Liying

# 或使用 venv
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate
```

### 3. 安装依赖

#### 安装 PyTorch (GPU 版本)

```bash
# CUDA 12.1 版本（推荐，兼容性更好）
pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121

# 或 CUDA 12.4 版本（最新）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

#### 安装其他依赖

```bash
# TTS 依赖
pip install -r install_tts_requirements.txt

# 或使用安装脚本（Windows）
install_tts_dependencies.bat
```

#### 安装其他 Python 依赖

```bash
pip install pymongo chromadb openai requests PyQt6 numpy librosa soundfile
```

### 4. 安装 MongoDB

#### Windows
下载并安装 MongoDB Community Server: https://www.mongodb.com/try/download/community

#### Linux
```bash
# Ubuntu/Debian
sudo apt-get install mongodb

# 或使用 Docker
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

#### macOS
```bash
brew install mongodb-community
brew services start mongodb-community
```

### 5. 配置 API 密钥

创建 `.env` 文件或设置环境变量：

```bash
# backtend/LLM/api_infer/config.py 或环境变量
export DEEPSEEK_API_KEY="your-api-key-here"
export BASE_URL="https://api.deepseek.com/v1"
export MODEL="deepseek-chat"
```

### 6. 下载模型

#### TTS 模型 (CosyVoice2-0.5B)

```python
# 使用 ModelScope
from modelscope import snapshot_download
snapshot_download('iic/CosyVoice2-0.5B', local_dir='backtend/models/TTS/CosyVoice2-0.5B')
```

#### 参考音频

将参考音频文件放置到以下位置之一：
- `backtend/TTS/Local/MagicMirror/backend/audio/zjj.wav`
- `Model/zjj.wav`
- `audio/zjj.wav`

### 7. 启动系统

#### 方式 1: 使用启动器（推荐）

```bash
# 启动 MongoDB + Live2D + 消息服务器
python launcher.py

# 调试模式
python launcher.py --debug
```

#### 方式 2: 手动启动

```bash
# 终端 1: 启动消息服务器
python message_server.py

# 终端 2: 启动 Live2D (通过 launcher)
python launcher.py

# 终端 3: 发送消息
python send_user_message.py "你好"
```

### 8. 测试系统

```bash
# 测试 TTS 模块
python test_tts.py

# 测试完整流程
python send_user_message.py "你好，介绍一下你自己"
```

---

## ⚙️ 详细配置

### LLM 配置

编辑 `backtend/LLM/api_infer/config.py`:

```python
DEEPSEEK_API_KEY = "your-api-key"
BASE_URL = "https://api.deepseek.com/v1"
MODEL = "deepseek-chat"
```

### MongoDB 配置

默认连接: `mongodb://localhost:27017/`

如需修改，编辑 `backtend/LLM/database/mongo_client.py`

### TTS 配置

#### 模型路径

默认路径: `backtend/models/TTS/CosyVoice2-0.5B`

修改 `send_user_message.py` 中的 `get_tts_engine()` 函数

#### GPU 配置

代码中已自动适配 4GB 显卡，强制关闭 JIT 和 TRT 优化：

```python
# 在 tts_engine.py 中已自动处理
if load_jit or load_trt:
    print("[WARN] 4GB 显卡不支持 JIT/TRT 优化，已强制关闭")
    load_jit = False
    load_trt = False
```

### Live2D 配置

编辑 `frontend/Live2DPet/src/main/java/com/live2d/Main.java`:

```java
// 窗口大小
int WINDOW_WIDTH = 800;
int WINDOW_HEIGHT = 600;

// 消息服务器地址
String MESSAGE_SERVER_URL = "http://localhost:8765";
```

---

## 📖 使用指南

### 基本使用

#### 1. 启动系统

```bash
# 启动所有服务
python launcher.py
```

系统会自动：
- ✅ 检查并启动 MongoDB
- ✅ 启动 Live2D 窗口
- ✅ 启动消息服务器

#### 2. 发送消息

```bash
# 方式 1: 命令行
python send_user_message.py "你好"

# 方式 2: 交互式
python send_user_message.py
# 然后输入消息
```

#### 3. 查看结果

- **Live2D 窗口**: AI 回复会显示在语音气泡中
- **控制台**: 显示详细的处理日志
- **音频文件**: 自动生成在 `audio_output/` 目录

### 高级功能

#### 1. 工具调用

Agent 支持多种工具，包括：
- 🔍 **搜索工具**: 网络搜索
- 💾 **记忆工具**: 保存/检索记忆
- 📸 **截图工具**: 截取屏幕
- 📅 **日期工具**: 获取当前时间

#### 2. 语音克隆

1. 准备参考音频文件（WAV 格式，16kHz）
2. 放置在 `backtend/TTS/Local/MagicMirror/backend/audio/` 目录
3. 系统会自动使用参考音频进行语音克隆

#### 3. 长期记忆

系统会自动提取对话中的重要信息，存储到长期记忆中：
- 用户偏好
- 重要事件
- 对话摘要

### 调试模式

```bash
# 启动调试模式，显示详细日志
python launcher.py --debug

# 查看 MongoDB 日志
tail -f logs/mongodb.log

# 查看 Agent 日志
tail -f logs/agent_*.log
```

---

## 🔧 开发说明

### 项目架构设计

#### 模块化设计

- **LLM 模块**: 独立的智能对话模块，可单独使用
- **TTS 模块**: 独立的语音合成模块，可单独使用
- **Live2D 模块**: 独立的虚拟形象模块，可单独使用

#### 消息传递机制

使用简单的 HTTP 协议实现模块间通信：
- **优点**: 简单、跨语言、易于调试
- **缺点**: 轮询机制有延迟

未来可考虑使用 WebSocket 实现实时通信。

#### 错误处理

- 所有模块都有完善的异常处理
- 关键操作都有日志记录
- 自动重试机制

### 代码规范

- **Python**: 遵循 PEP 8 规范
- **Java**: 遵循 Google Java Style Guide
- **注释**: 关键函数都有文档字符串

### 测试

```bash
# 测试 TTS 模块
python test_tts.py

# 测试 LLM 模块
python backtend/LLM/test_agent.py

# 测试完整流程
python send_user_message.py "测试消息"
```

### 扩展开发

#### 添加新工具

1. 在 `backtend/LLM/tools/` 创建新工具类
2. 继承 `BaseTool` 类
3. 实现 `execute()` 方法
4. 在 `agent.py` 中注册工具

#### 添加新模型

1. 在 `backtend/models/` 添加模型文件
2. 修改相应模块的加载逻辑
3. 更新配置文件

---

## ❓ 常见问题

### Q1: Live2D 窗口不显示？

**A**: 检查以下几点：
1. Java 版本是否正确 (需要 Java 17+)
2. Maven 是否正确构建项目
3. 查看 `launcher.py` 的输出日志
4. 尝试调试模式: `python launcher.py --debug`

### Q2: TTS 初始化失败？

**A**: 
1. 检查模型路径是否正确
2. 检查 CUDA 和 PyTorch 是否正确安装
3. 查看 `test_tts.py` 的详细错误信息
4. 确认显卡驱动版本正确

### Q3: 语音生成太慢？

**A**:
1. 确认使用 GPU 加速 (检查 `torch.cuda.is_available()`)
2. 考虑升级显卡
3. 减少并行处理的线程数（在 `tts_engine.py` 中）

### Q4: MongoDB 连接失败？

**A**:
1. 确认 MongoDB 服务已启动
2. 检查连接字符串是否正确
3. 检查防火墙设置
4. 查看 MongoDB 日志

### Q5: DeepSeek API 调用失败？

**A**:
1. 检查 API 密钥是否正确
2. 检查网络连接
3. 查看 API 余额
4. 检查请求频率限制

---

## ⚡ 性能优化

### GPU 加速

- **PyTorch**: 已启用 CUDA 加速
- **显存优化**: 自动适配 4GB 显卡，关闭 JIT/TRT
- **批量处理**: TTS 使用并行处理加速

### 内存优化

- **延迟加载**: 模型按需加载，避免启动时占用过多内存
- **内存回收**: 及时清理不需要的张量
- **流式处理**: 使用生成器减少内存占用

### 速度优化

- **并行处理**: TTS 多线程并行生成
- **缓存机制**: 音色特征缓存，避免重复提取
- **连接复用**: HTTP 连接复用

---

## 🗺️ 路线图

### 已完成 ✅
- [x] LLM 模块开发
- [x] Live2D 集成
- [x] TTS 模块集成
- [x] 消息服务器
- [x] 基础工具调用
- [x] 记忆管理

### 进行中 🚧
- [ ] WebSocket 实时通信
- [ ] 更多工具集成
- [ ] 性能优化

### 计划中 📋
- [ ] Web 前端界面
- [ ] 语音识别 (ASR)
- [ ] 多模态交互
- [ ] 插件系统
- [ ] 云端部署

---

## 📄 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE) 文件。

---

## 🙏 致谢

- [Live2D Cubism SDK](https://www.live2d.com/) - 虚拟形象渲染
- [CosyVoice2](https://github.com/FunAudioLLM/CosyVoice-2) - 语音合成模型
- [DeepSeek](https://www.deepseek.com/) - 大语言模型 API
- [ChromaDB](https://www.trychroma.com/) - 向量数据库
- [MongoDB](https://www.mongodb.com/) - 数据库

---

## 📧 联系方式

如有问题或建议，欢迎：
- 提交 Issue
- 发送邮件
- 参与讨论

---

**Made with ❤️ by Liying Team**

