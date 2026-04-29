# 玲 (Liying) - 部署指南

本文档提供完整的一键部署指南，帮助你快速部署玲智能虚拟助手系统。

---

## 📋 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [详细步骤](#详细步骤)
- [配置说明](#配置说明)
- [常见问题](#常见问题)
- [高级配置](#高级配置)

---

## 🖥️ 系统要求

### 最低要求

- **操作系统**: Windows 10/11, Ubuntu 20.04+, macOS 11+
- **Python**: 3.8+
- **内存**: 8GB RAM
- **磁盘**: 10GB 可用空间
- **网络**: 稳定的互联网连接（用于 API 调用和模型下载）

### 推荐配置

- **操作系统**: Windows 11, Ubuntu 22.04, macOS 13+
- **Python**: 3.12
- **Java**: 17+ (用于 Live2D)
- **内存**: 16GB RAM
- **显卡**: NVIDIA GPU，4GB+ 显存（用于 TTS 加速）
- **CUDA**: 12.1+ (如果使用 GPU)
- **磁盘**: 20GB 可用空间

### 可选组件

- **MongoDB**: 用于数据存储（可使用 Docker）
- **Maven**: 用于编译 Live2D（可使用预编译 JAR）
- **Docker**: 用于容器化部署

---

## 🚀 快速开始

### Linux/macOS

```bash
# 1. 克隆项目
git clone <repository-url>
cd Liying

# 2. 一键安装
bash deploy.sh install

# 3. 配置环境变量
# 编辑 .env 文件，填写 API Key 等配置
nano .env

# 4. 启动系统
bash deploy.sh start

# 5. 查看状态
bash deploy.sh status
```

### Windows

```powershell
# 1. 克隆项目
git clone <repository-url>
cd Liying

# 2. 一键安装
.\deploy.ps1 install

# 3. 配置环境变量
# 编辑 .env 文件，填写 API Key 等配置
notepad .env

# 4. 启动系统
.\deploy.ps1 start

# 5. 查看状态
.\deploy.ps1 status
```

---

## 📝 详细步骤

### 步骤 1: 安装依赖

部署脚本会自动检查并安装以下依赖：

#### 自动检查项

- ✅ Python 版本（需要 3.8+）
- ✅ Java 版本（需要 17+，用于 Live2D）
- ✅ Maven（可选，用于编译 Live2D）
- ✅ MongoDB（可选，可使用 Docker）

#### 自动安装项

- ✅ Python 虚拟环境
- ✅ PyTorch (CUDA 12.1)
- ✅ 所有 Python 依赖
- ✅ Live2D 编译（如果有 Maven）

#### Linux/macOS

```bash
bash deploy.sh install
```

#### Windows

```powershell
.\deploy.ps1 install
```

### 步骤 2: 配置环境变量

安装完成后，会自动创建 `.env` 文件（从 `.env.example` 复制）。

#### 必需配置

编辑 `.env` 文件，填写以下必需配置：

```bash
# LLM API 配置（必需）
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4
```

#### 可选配置

```bash
# MongoDB 配置
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=liying_db

# TTS 配置
LIYING_TTS_REMOTE_URL=http://127.0.0.1:18888
LIYING_TTS_SPK_ID=玲

# 模型缓存目录（推荐设置，避免下载到 C 盘）
HF_HOME=./.hf_cache
MODELSCOPE_CACHE=./.modelscope_cache
```

### 步骤 3: 启动 MongoDB（可选）

如果你已经有 MongoDB 服务，可以跳过此步骤。

#### 方式 1: 使用部署脚本启动

```bash
# Linux/macOS
bash deploy.sh start-mongodb

# Windows
.\deploy.ps1 start-mongodb
```

#### 方式 2: 使用 Docker

```bash
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

#### 方式 3: 手动启动

- **Windows**: 启动 MongoDB 服务
- **Linux**: `sudo systemctl start mongodb`
- **macOS**: `brew services start mongodb-community`

### 步骤 4: 初始化数据库

```bash
# Linux/macOS
bash deploy.sh init-db

# Windows
.\deploy.ps1 init-db
```

这会创建必要的数据库索引和默认数据。

### 步骤 5: 启动系统

```bash
# Linux/macOS
bash deploy.sh start

# Windows
.\deploy.ps1 start
```

系统会自动启动：
- ✅ MongoDB（如果未运行）
- ✅ 主程序（包括 GUI、Live2D、对话系统）

### 步骤 6: 验证部署

#### 查看状态

```bash
# Linux/macOS
bash deploy.sh status

# Windows
.\deploy.ps1 status
```

#### 查看日志

```bash
# Linux/macOS
bash deploy.sh logs

# Windows
.\deploy.ps1 logs
```

#### 预期输出

```
========================================
  玲 (Liying) - 智能虚拟助手系统
========================================

检查服务状态...

[SUCCESS] MongoDB: 运行中 (PID: 1234)
[SUCCESS] 主程序: 运行中 (PID: 5678)
```

---

## ⚙️ 配置说明

### 环境变量详解

#### LLM 配置

```bash
# API 地址
OPENAI_API_BASE=https://api.openai.com/v1

# API 密钥（必需）
OPENAI_API_KEY=sk-xxxxx

# 模型名称
OPENAI_MODEL=gpt-4

# 或使用 DeepSeek
# OPENAI_API_BASE=https://api.deepseek.com/v1
# OPENAI_API_KEY=your_deepseek_key
# OPENAI_MODEL=deepseek-chat
```

#### MongoDB 配置

```bash
# 连接地址
MONGODB_URI=mongodb://localhost:27017

# 数据库名称
MONGODB_DB=liying_db

# 连接超时（可选）
# MONGODB_TIMEOUT_MS=5000
```

#### TTS 配置

```bash
# 远程 TTS 服务地址（可选）
LIYING_TTS_REMOTE_URL=http://127.0.0.1:18888

# 说话人 ID
LIYING_TTS_SPK_ID=玲

# 本地 TTS 模型路径（可选）
# LIYING_TTS_MODEL_DIR=./models/TTS/CosyVoice2-0.5B
```

#### 模型缓存配置

```bash
# HuggingFace 模型缓存（强烈推荐设置）
HF_HOME=./.hf_cache

# ModelScope 模型缓存
MODELSCOPE_CACHE=./.modelscope_cache
```

### 目录结构

部署后的目录结构：

```
Liying/
├── venv/                  # Python 虚拟环境
├── logs/                  # 日志文件
│   ├── main.log          # 主程序日志
│   ├── mongodb.log       # MongoDB 日志
│   └── main_error.log    # 错误日志
├── .pids/                # PID 文件
│   ├── mongodb.pid       # MongoDB PID
│   └── main.pid          # 主程序 PID
├── models/               # 模型文件
│   ├── TTS/             # TTS 模型
│   └── ASR/             # ASR 模型
├── data/                 # 数据目录
│   ├── chroma_data/     # 向量数据库
│   ├── dreams/          # 梦境日记
│   ├── screenshots/     # 截图
│   └── mongodb/         # MongoDB 数据
└── .env                  # 环境变量配置
```

---

## 🔧 常见问题

### Q1: Python 版本过低

**问题**: `Python 版本过低，需要 3.8+`

**解决**:
```bash
# 安装 Python 3.12
# Ubuntu/Debian
sudo apt-get install python3.12

# macOS
brew install python@3.12

# Windows
# 从 https://www.python.org/downloads/ 下载安装
```

### Q2: MongoDB 连接失败

**问题**: `MongoDB 连接失败`

**解决**:
1. 检查 MongoDB 是否运行：
   ```bash
   # Linux/macOS
   ps aux | grep mongod
   
   # Windows
   tasklist | findstr mongod
   ```

2. 使用 Docker 启动 MongoDB：
   ```bash
   docker run -d -p 27017:27017 --name mongodb mongo:latest
   ```

3. 检查 `.env` 中的 `MONGODB_URI` 配置

### Q3: Live2D 无法启动

**问题**: `Live2D 启动失败`

**解决**:
1. 检查 Java 版本：
   ```bash
   java -version
   # 需要 Java 17+
   ```

2. 安装 Java 17：
   ```bash
   # Ubuntu/Debian
   sudo apt-get install openjdk-17-jdk
   
   # macOS
   brew install openjdk@17
   
   # Windows
   # 从 https://adoptium.net/ 下载安装
   ```

3. 使用预编译的 JAR（如果有）

### Q4: GPU 加速不可用

**问题**: `CUDA 不可用，使用 CPU`

**解决**:
1. 检查 CUDA 版本：
   ```bash
   nvidia-smi
   ```

2. 安装 CUDA 12.1：
   - 下载地址: https://developer.nvidia.com/cuda-downloads

3. 重新安装 PyTorch：
   ```bash
   pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121
   ```

### Q5: 模型下载失败

**问题**: `模型下载失败或速度慢`

**解决**:
1. 设置镜像源：
   ```bash
   # HuggingFace 镜像
   export HF_ENDPOINT=https://hf-mirror.com
   
   # ModelScope 镜像（国内）
   export MODELSCOPE_CACHE=./.modelscope_cache
   ```

2. 手动下载模型：
   - TTS 模型: https://modelscope.cn/models/iic/CosyVoice2-0.5B
   - ASR 模型: https://modelscope.cn/models/damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch

3. 放置到对应目录：
   ```
   models/TTS/CosyVoice2-0.5B/
   models/ASR/paraformer-zh-streaming/
   ```

### Q6: 权限不足

**问题**: `Permission denied`

**解决**:
```bash
# Linux/macOS
chmod +x deploy.sh
bash deploy.sh install

# Windows
# 以管理员身份运行 PowerShell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\deploy.ps1 install
```

---

## 🎯 高级配置

### 使用远程 TTS 服务

如果你有独立的 TTS 服务器：

1. 启动 TTS 服务器：
   ```bash
   cd deploy/tts_server
   bash deploy.sh install
   bash deploy.sh start
   ```

2. 配置 `.env`：
   ```bash
   LIYING_TTS_REMOTE_URL=http://your-tts-server:5001
   ```

### 使用远程 ASR 服务

如果你有独立的 ASR 服务器：

1. 启动 ASR 服务器：
   ```bash
   cd deploy/asr_server
   bash deploy.sh install
   bash deploy.sh start
   ```

2. 配置代码中的 ASR 地址

### Docker 部署（推荐）

使用 Docker Compose 一键部署所有服务：

```bash
# 创建 docker-compose.yml（待实现）
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 生产环境部署

#### 使用 systemd（Linux）

创建 systemd 服务文件：

```bash
sudo nano /etc/systemd/system/liying.service
```

内容：

```ini
[Unit]
Description=Liying AI Assistant
After=network.target mongodb.service

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/Liying
ExecStart=/path/to/Liying/venv/bin/python /path/to/Liying/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable liying
sudo systemctl start liying
sudo systemctl status liying
```

#### 使用 Windows 服务

使用 NSSM (Non-Sucking Service Manager)：

```powershell
# 下载 NSSM
# https://nssm.cc/download

# 安装服务
nssm install Liying "C:\path\to\Liying\venv\Scripts\python.exe" "C:\path\to\Liying\main.py"

# 启动服务
nssm start Liying

# 查看状态
nssm status Liying
```

---

## 📊 部署脚本命令参考

### Linux/macOS

```bash
bash deploy.sh [命令]
```

### Windows

```powershell
.\deploy.ps1 [命令]
```

### 可用命令

| 命令 | 说明 |
|------|------|
| `install` | 安装依赖和配置环境 |
| `start` | 启动所有服务 |
| `stop` | 停止所有服务 |
| `restart` | 重启所有服务 |
| `status` | 查看服务状态 |
| `logs` | 查看日志（实时） |
| `start-mongodb` | 仅启动 MongoDB |
| `stop-mongodb` | 仅停止 MongoDB |
| `init-db` | 初始化数据库 |
| `clean` | 清理所有数据和缓存 |
| `help` | 显示帮助信息 |

---

## 🎉 部署完成

部署完成后，你应该能看到：

1. ✅ **GUI 窗口**: 系统托盘图标
2. ✅ **Live2D 窗口**: 虚拟形象窗口
3. ✅ **对话功能**: 可以通过语音或文字与 AI 对话

### 测试系统

1. **测试文字对话**:
   ```bash
   python main.py --text
   ```

2. **测试 GUI**:
   ```bash
   python main.py
   ```

3. **测试 TTS**:
   ```bash
   python scripts/test_tts.py
   ```

---

## 📞 获取帮助

如果遇到问题：

1. 查看日志文件：`logs/main.log`
2. 查看错误日志：`logs/main_error.log`
3. 运行诊断：`bash deploy.sh status`
4. 提交 Issue 或联系开发团队

---

**祝你部署顺利！🎊**
