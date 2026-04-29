# ASR 服务器

统一的语音识别服务，支持 ASR、SER、SV、Diarization、PUNC、VAD。

---

## 🚀 快速开始

### 方法 1: 一键部署脚本（推荐）

#### Linux/macOS

```bash
# 1. 安装
bash deploy/asr_server/deploy.sh install

# 2. 启动
bash deploy/asr_server/deploy.sh start

# 3. 查看状态
bash deploy/asr_server/deploy.sh status

# 4. 查看日志
bash deploy/asr_server/deploy.sh logs
```

#### Windows

```powershell
# 1. 安装
.\deploy\asr_server\deploy.ps1 install

# 2. 启动
.\deploy\asr_server\deploy.ps1 start

# 3. 查看状态
.\deploy\asr_server\deploy.ps1 status

# 4. 查看日志
.\deploy\asr_server\deploy.ps1 logs
```

### 方法 2: Docker 部署

```bash
# 使用 Docker Compose
cd deploy/asr_server
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 方法 3: 手动部署

```bash
# 1. 安装依赖
pip install -r deploy/asr_server/requirements.txt

# 2. 启动服务器
python deploy/asr_server/server.py --host 0.0.0.0 --port 5002
```

---

## 📡 API 端点

### 健康检查
```bash
curl http://localhost:5002/health
```

### ASR 识别
```bash
# 离线识别
curl -X POST http://localhost:5002/asr/recognize \
  -H "Content-Type: application/json" \
  -d '{"audio": "base64_encoded_wav"}'

# 流式识别
# 1. 开始会话
curl -X POST http://localhost:5002/asr/stream/start

# 2. 发送音频块
curl -X POST http://localhost:5002/asr/stream/feed \
  -H "Content-Type: application/json" \
  -d '{"session_id": "xxx", "audio": "base64_encoded_audio", "is_final": false}'

# 3. 取消会话
curl -X POST http://localhost:5002/asr/stream/cancel \
  -H "Content-Type: application/json" \
  -d '{"session_id": "xxx"}'
```

### 其他功能
- `POST /ser/recognize` - 情绪识别
- `POST /sv/extract` - 声纹提取
- `POST /diarization/identify` - 说话人识别
- `POST /punc/restore` - 标点恢复
- `POST /vad/detect` - VAD 检测
- `POST /all/process` - 一站式处理

---

## 📚 文档

- [快速开始](./QUICK_START.md) - 5 分钟快速部署
- [部署指南](./DEPLOYMENT_GUIDE.md) - 完整部署文档
- [客户端示例](./client_example.py) - Python 客户端示例

---

## 🔧 配置

### 环境变量

```bash
# GPU 设备
export CUDA_VISIBLE_DEVICES=0

# 模型缓存目录
export FUNASR_CACHE_DIR=/path/to/cache
```

### 服务器配置

编辑 `server.py` 中的配置：

```python
config = ASRConfig(
    device="cuda:0",  # 或 "cpu"
    chunk_size=[0, 10, 5],  # 流式配置
    use_vad=True,
    max_end_sil=800,
)
```

---

## 🐛 故障排查

### 服务器无法启动

**检查**:
- Python 版本 >= 3.8
- 依赖已安装
- 端口未被占用

### 识别结果为空

**检查**:
- 音频格式正确（WAV, 16kHz, 单声道）
- 音频质量良好
- 查看服务器日志

### 连接超时

**检查**:
- 服务器地址正确
- 防火墙允许端口 5002
- 网络连接正常

---

## 📊 性能

### 硬件要求

- **CPU**: 4 核心+
- **内存**: 8GB+ (推荐 16GB+)
- **GPU**: 可选，NVIDIA GPU with CUDA 11.0+

### 性能指标

- **ASR 首包延迟**: ~100ms
- **ASR RTF**: ~0.3
- **并发支持**: 4-8 个并发请求（取决于硬件）

---

## 🔒 安全

### 生产环境建议

1. **使用 HTTPS**: 配置 Nginx 反向代理
2. **API 认证**: 添加 API Key 验证
3. **速率限制**: 使用 Flask-Limiter
4. **防火墙**: 限制访问 IP

---

## 📝 许可证

本项目遵循项目根目录的许可证。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📞 支持

如有问题，请查看文档或提交 Issue。
