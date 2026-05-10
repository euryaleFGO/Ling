# ASR 服务器部署指南

**更新时间**: 2026-05-08
**版本**: 1.1

---

## 📋 概述

ASR 服务器提供统一的语音识别服务，包括：
- **ASR**: 语音识别（支持流式和离线）
- **SER**: 情绪识别
- **SV**: 声纹提取
- **Diarization**: 说话人识别
- **PUNC**: 标点恢复
- **VAD**: 语音活动检测

---

## 🚀 快速开始

### 一键部署（推荐）

本部署包提供一键部署脚本，自动完成环境配置、依赖安装和模型下载：

#### Linux/macOS

```bash
# 解压部署包
unzip asr_server_deploy.zip
cd asr_server

# 一键部署（CPU 版本）
bash setup.sh

# 或 GPU 版本
bash setup.sh --gpu

# 启动服务
bash start.sh
```

#### Windows

```cmd
# 解压部署包
# 双击运行 setup.bat
# 或命令行：
setup.bat

# 启动服务
start.bat
```

### 手动部署

如需手动控制每个步骤：

#### 1. 环境准备

##### 系统要求
- **操作系统**: Linux (推荐 Ubuntu 20.04+) 或 Windows Server
- **Python**: 3.8+
- **内存**: 8GB+ (推荐 16GB+)
- **GPU**: 可选，NVIDIA GPU with CUDA 11.0+ (推荐用于加速)

##### 安装依赖

```bash
# 进入项目目录
cd /path/to/Liying

# 安装 Python 依赖
pip install -r requirements.txt

# 如果使用 GPU
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 2. 模型准备

#### 下载模型

ASR 服务器需要以下模型：

1. **Paraformer 流式模型** (必需)
   ```bash
   # 自动下载（首次运行时）
   # 或手动下载到 models/ASR/paraformer-zh-streaming/
   ```

2. **VAD 模型** (推荐)
   ```bash
   # 自动下载（首次运行时）
   # 或手动下载到 models/ASR/fsmn-vad/
   ```

3. **其他模型** (可选)
   - SER 模型: `models/SER/`
   - SV 模型: `models/SV/`
   - PUNC 模型: `models/PUNC/`

#### 模型目录结构

```
models/
├── ASR/
│   ├── paraformer-zh-streaming/
│   │   ├── model.pt
│   │   ├── config.yaml
│   │   └── ...
│   └── fsmn-vad/
│       ├── model.pt
│       └── ...
├── SER/
│   └── ...
├── SV/
│   └── ...
└── PUNC/
    └── ...
```

### 3. 启动服务器

#### 开发模式

```bash
python deploy/asr_server/server.py --host 0.0.0.0 --port 5002 --debug
```

#### 生产模式（使用 Gunicorn）

```bash
# 安装 Gunicorn
pip install gunicorn

# 启动服务器（4 个 worker）
cd deploy/asr_server
gunicorn -w 4 -b 0.0.0.0:5002 --timeout 300 server:app
```

#### 使用 systemd 管理（推荐）

创建服务文件 `/etc/systemd/system/asr-server.service`:

```ini
[Unit]
Description=ASR Server
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/Liying/deploy/asr_server
Environment="PATH=/path/to/python/bin"
ExecStart=/path/to/python/bin/gunicorn -w 4 -b 0.0.0.0:5002 --timeout 300 server:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable asr-server
sudo systemctl start asr-server
sudo systemctl status asr-server
```

---

## 📡 API 文档

### 健康检查

```http
GET /health
```

**响应**:
```json
{
  "status": "ok",
  "service": "ASR Server"
}
```

### ASR 离线识别

识别整段音频（非流式）。

```http
POST /asr/recognize
Content-Type: application/json

{
  "audio": "base64编码的WAV音频",
  "sample_rate": 16000
}
```

**响应**:
```json
{
  "status": "success",
  "text": "识别的文本内容",
  "duration": 1.23
}
```

### ASR 流式识别

#### 1. 开始流式会话

```http
POST /asr/stream/start
Content-Type: application/json

{
  "session_id": "optional_session_id"
}
```

**响应**:
```json
{
  "status": "success",
  "session_id": "session_123",
  "chunk_size": 9600
}
```

#### 2. 发送音频块

```http
POST /asr/stream/feed
Content-Type: application/json

{
  "session_id": "session_123",
  "audio": "base64编码的音频数据（float32）",
  "is_final": false
}
```

**响应**:
```json
{
  "status": "success",
  "text": "当前识别结果",
  "is_final": false
}
```

#### 3. 取消会话

```http
POST /asr/stream/cancel
Content-Type: application/json

{
  "session_id": "session_123"
}
```

**响应**:
```json
{
  "status": "success"
}
```

### 其他 API

- **SER 情绪识别**: `POST /ser/recognize`
- **SV 声纹提取**: `POST /sv/extract`
- **说话人识别**: `POST /diarization/identify`
- **标点恢复**: `POST /punc/restore`
- **VAD 检测**: `POST /vad/detect`
- **一站式处理**: `POST /all/process`

详细 API 文档请参考 `API_REFERENCE.md`。

---

## 🔧 配置

### 环境变量

```bash
# GPU 设备（可选）
export CUDA_VISIBLE_DEVICES=0

# 模型缓存目录（可选）
export FUNASR_CACHE_DIR=/path/to/cache
```

### 服务器配置

编辑 `server.py` 中的配置：

```python
# ASR 配置
config = ASRConfig(
    device="cuda:0",  # 或 "cpu"
    chunk_size=[0, 10, 5],  # 流式配置
    use_vad=True,
    max_end_sil=800,
)
```

---

## 🐳 Docker 部署

### 构建镜像

创建 `Dockerfile`:

```dockerfile
FROM python:3.10-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY . /app

# 安装 Python 依赖
RUN pip install --no-cache-dir -r deploy/asr_server/requirements.txt

# 暴露端口
EXPOSE 5002

# 启动服务器
CMD ["python", "deploy/asr_server/server.py", "--host", "0.0.0.0", "--port", "5002"]
```

构建和运行：

```bash
# 构建镜像
docker build -t asr-server:latest .

# 运行容器
docker run -d \
  --name asr-server \
  -p 5002:5002 \
  -v /path/to/models:/app/models \
  asr-server:latest
```

### 使用 Docker Compose

创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  asr-server:
    build: .
    ports:
      - "5002:5002"
    volumes:
      - ./models:/app/models
      - ./data:/app/data
    environment:
      - CUDA_VISIBLE_DEVICES=0
    restart: unless-stopped
```

启动：

```bash
docker-compose up -d
```

---

## 📊 性能优化

### 1. GPU 加速

使用 GPU 可以显著提升性能：

```python
config = ASRConfig(
    device="cuda:0",  # 使用第一个 GPU
)
```

### 2. 批处理

对于离线识别，可以使用批处理：

```python
# 在 server.py 中修改
res = self._model_offline.generate(
    input=audio_list,  # 多个音频
    batch_size_s=300,
)
```

### 3. Worker 数量

根据 CPU 核心数调整 Gunicorn worker 数量：

```bash
# 推荐: (2 * CPU核心数) + 1
gunicorn -w 9 -b 0.0.0.0:5002 server:app
```

### 4. 模型缓存

首次加载后，模型会常驻内存，避免重复加载。

---

## 🔍 监控和日志

### 日志配置

服务器使用 Python logging，日志级别为 INFO。

查看日志：

```bash
# systemd 服务
sudo journalctl -u asr-server -f

# Docker 容器
docker logs -f asr-server
```

### 性能监控

使用 Prometheus + Grafana 监控：

1. 安装 `prometheus-flask-exporter`:
   ```bash
   pip install prometheus-flask-exporter
   ```

2. 在 `server.py` 中添加：
   ```python
   from prometheus_flask_exporter import PrometheusMetrics
   metrics = PrometheusMetrics(app)
   ```

3. 访问 `http://server:5002/metrics` 查看指标

---

## 🐛 故障排查

### 常见问题

#### 1. 模型加载失败

**错误**: `FileNotFoundError: 模型文件不存在`

**解决方法**:
- 检查模型目录是否正确
- 确保模型文件已下载
- 检查文件权限

#### 2. CUDA 错误

**错误**: `RuntimeError: CUDA out of memory`

**解决方法**:
- 减少 worker 数量
- 使用 CPU 模式
- 增加 GPU 内存

#### 3. 流式识别会话丢失

**错误**: `会话不存在`

**解决方法**:
- 检查会话 ID 是否正确
- 会话超时时间为 5 分钟，超时后自动清理
- 确保客户端正确管理会话

#### 4. 识别结果为空

**可能原因**:
- 音频质量差
- 音频格式不正确
- VAD 检测到无语音

**解决方法**:
- 检查音频采样率（应为 16kHz）
- 检查音频格式（应为 float32 或 int16）
- 调整 VAD 参数

---

## 🔒 安全建议

### 1. 使用 HTTPS

使用 Nginx 反向代理并配置 SSL：

```nginx
server {
    listen 443 ssl;
    server_name asr.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 2. API 认证

添加 API Key 认证：

```python
from functools import wraps

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != os.environ.get('ASR_API_KEY'):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/asr/recognize', methods=['POST'])
@require_api_key
def asr_recognize():
    # ...
```

### 3. 速率限制

使用 Flask-Limiter 限制请求频率：

```python
from flask_limiter import Limiter

limiter = Limiter(
    app,
    key_func=lambda: request.remote_addr,
    default_limits=["100 per hour"]
)

@app.route('/asr/recognize', methods=['POST'])
@limiter.limit("10 per minute")
def asr_recognize():
    # ...
```

---

## 📚 相关文档

- [API 参考文档](./API_REFERENCE.md)
- [客户端示例](./client_example.py)
- [性能基准测试](./BENCHMARKS.md)

---

## 🎉 总结

ASR 服务器提供了完整的语音识别服务，支持：

✅ **流式识别** - 实时语音识别  
✅ **离线识别** - 整段音频识别  
✅ **多功能** - ASR、SER、SV、Diarization、PUNC、VAD  
✅ **高性能** - GPU 加速、批处理、模型缓存  
✅ **易部署** - Docker、systemd、Gunicorn  
✅ **可扩展** - RESTful API、会话管理

**下一步**: 部署到生产环境，配置监控和日志！
