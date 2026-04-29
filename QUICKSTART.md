# 快速开始指南

**5 分钟快速部署玲 (Liying) 智能虚拟助手系统**

---

## 🚀 Linux/macOS 用户

```bash
# 1. 克隆项目
git clone <repository-url>
cd Liying

# 2. 一键安装
bash deploy.sh install

# 3. 配置 API Key
nano .env
# 填写: OPENAI_API_KEY=your_key_here

# 4. 启动系统
bash deploy.sh start

# 5. 完成！
```

---

## 🚀 Windows 用户

```powershell
# 1. 克隆项目
git clone <repository-url>
cd Liying

# 2. 一键安装
.\deploy.ps1 install

# 3. 配置 API Key
notepad .env
# 填写: OPENAI_API_KEY=your_key_here

# 4. 启动系统
.\deploy.ps1 start

# 5. 完成！
```

---

## 📋 必需配置

编辑 `.env` 文件，填写以下配置：

```bash
# LLM API 配置（必需）
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4

# 或使用 DeepSeek
# OPENAI_API_BASE=https://api.deepseek.com/v1
# OPENAI_API_KEY=your_deepseek_key
# OPENAI_MODEL=deepseek-chat
```

---

## 🎯 常用命令

### Linux/macOS

```bash
bash deploy.sh start    # 启动系统
bash deploy.sh stop     # 停止系统
bash deploy.sh status   # 查看状态
bash deploy.sh logs     # 查看日志
bash deploy.sh restart  # 重启系统
```

### Windows

```powershell
.\deploy.ps1 start    # 启动系统
.\deploy.ps1 stop     # 停止系统
.\deploy.ps1 status   # 查看状态
.\deploy.ps1 logs     # 查看日志
.\deploy.ps1 restart  # 重启系统
```

---

## ❓ 遇到问题？

### 问题 1: Python 版本过低

```bash
# 安装 Python 3.12
# Ubuntu: sudo apt-get install python3.12
# macOS: brew install python@3.12
# Windows: 从 python.org 下载安装
```

### 问题 2: MongoDB 连接失败

```bash
# 使用 Docker 启动 MongoDB
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

### 问题 3: 需要帮助

查看完整文档：
- [DEPLOYMENT.md](DEPLOYMENT.md) - 完整部署指南
- [README.md](README.md) - 项目文档

---

## 🎉 部署成功！

系统启动后，你应该能看到：

1. ✅ **GUI 窗口** - 系统托盘图标
2. ✅ **Live2D 窗口** - 虚拟形象
3. ✅ **对话功能** - 可以开始对话

---

**祝你使用愉快！** 🎊
