# ASR 服务器部署包

## 📦 包含文件

```
asr_server_deploy/
├── server.py           # ASR 服务器主程序
├── requirements.txt    # Python 依赖
├── setup.sh           # Linux/macOS 一键部署脚本
├── setup.bat          # Windows 一键部署脚本
├── Dockerfile         # Docker 部署（可选）
├── docker-compose.yml # Docker Compose（可选）
├── client_example.py  # 客户端示例
└── DEPLOYMENT_GUIDE.md # 详细部署指南
```

## 🚀 快速部署

### Linux/macOS

```bash
# 1. 解压部署包
unzip asr_server_deploy.zip
cd asr_server_deploy

# 2. 一键部署（CPU 版本）
bash setup.sh

# 或 GPU 版本
bash setup.sh --gpu

# 3. 启动服务
bash start.sh
```

### Windows

```cmd
# 1. 解压部署包
# 2. 双击运行 setup.bat
# 或命令行：
setup.bat

# 3. 启动服务
start.bat
```

### Docker（推荐）

```bash
# 1. 构建镜像
docker build -t asr-server .

# 2. 运行容器
docker run -d \
  --name asr-server \
  -p 5002:5002 \
  -v ./models:/app/models \
  asr-server

# 或使用 Docker Compose
docker-compose up -d
```

## 📋 系统要求

- **Python**: 3.8+
- **内存**: 8GB+ (推荐 16GB+)
- **磁盘**: 5GB+ (用于模型)
- **GPU** (可选): NVIDIA GPU with CUDA 11.0+

## 🔧 配置选项

### 环境变量

```bash
# GPU 设备（可选）
export CUDA_VISIBLE_DEVICES=0

# 模型缓存目录（可选）
export FUNASR_CACHE_DIR=/path/to/cache
```

### 命令行参数

```bash
python server.py --help

# 选项：
#   --host HOST    监听地址 (默认: 0.0.0.0)
#   --port PORT    监听端口 (默认: 5002)
#   --device DEV   设备: auto/cuda/cpu (默认: auto)
#   --debug        调试模式
```

## 🧪 验证部署

```bash
# 健康检查
curl http://localhost:5002/health

# 测试识别
python client_example.py
```

## 📊 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/asr/recognize` | POST | 离线识别 |
| `/asr/stream/start` | POST | 开始流式识别 |
| `/asr/stream/feed` | POST | 流式输入音频 |
| `/asr/stream/end` | POST | 结束流式识别 |
| `/asr/stream/cancel` | POST | 取消流式识别 |

## 🔍 故障排查

### 模型下载失败

```bash
# 手动下载模型
python -c "
from modelscope.hub.snapshot_download import snapshot_download
snapshot_download('iic/speech_paraformer-zh-streaming', local_dir='models/ASR/paraformer-zh-streaming')
"
```

### CUDA 内存不足

```bash
# 使用 CPU 模式
python server.py --device cpu

# 或减少 worker 数量
gunicorn -w 2 -b 0.0.0.0:5002 server:app
```

### 端口被占用

```bash
# 查找占用端口的进程
lsof -i :5002  # Linux/macOS
netstat -ano | findstr :5002  # Windows

# 使用其他端口
python server.py --port 5003
```

## 📚 更多文档

- [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - 详细部署指南
- [API_REFERENCE.md](./API_REFERENCE.md) - API 参考文档

## 🤝 技术支持

- GitHub Issues: [项目地址]
- 文档: [文档地址]

---

**部署愉快！** 🎉
