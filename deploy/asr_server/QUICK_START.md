# ASR 服务器快速开始

**5 分钟部署 ASR 服务器**

---

## 🚀 快速部署

### 1. 安装依赖

```bash
cd /path/to/Liying
pip install -r deploy/asr_server/requirements.txt
```

### 2. 启动服务器

```bash
python deploy/asr_server/server.py --host 0.0.0.0 --port 5002
```

服务器将在 `http://0.0.0.0:5002` 启动。

### 3. 测试服务器

```bash
# 健康检查
curl http://localhost:5002/health

# 运行客户端示例
python deploy/asr_server/client_example.py
```

---

## 📡 API 使用

### 离线识别

```python
import requests
import base64

# 读取音频文件
with open("audio.wav", "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode()

# 发送请求
response = requests.post(
    "http://localhost:5002/asr/recognize",
    json={"audio": audio_b64}
)

result = response.json()
print(result["text"])
```

### 流式识别

```python
# 1. 开始会话
response = requests.post(
    "http://localhost:5002/asr/stream/start",
    json={}
)
session_id = response.json()["session_id"]

# 2. 发送音频块
for chunk in audio_chunks:
    audio_b64 = base64.b64encode(chunk.tobytes()).decode()
    response = requests.post(
        "http://localhost:5002/asr/stream/feed",
        json={
            "session_id": session_id,
            "audio": audio_b64,
            "is_final": False
        }
    )
    print(response.json()["text"])

# 3. 结束会话
response = requests.post(
    "http://localhost:5002/asr/stream/feed",
    json={
        "session_id": session_id,
        "audio": empty_audio_b64,
        "is_final": True
    }
)
print("最终结果:", response.json()["text"])
```

---

## 🔧 配置客户端

在你的客户端代码中，设置 ASR 服务器地址：

```python
# 在 .env 文件中
LIYING_ASR_REMOTE_URL=http://your-server:5002

# 或在代码中
from backend.asr.asr_client import ASRClient
asr_client = ASRClient("http://your-server:5002")
```

---

## 📚 更多文档

- [完整部署指南](./DEPLOYMENT_GUIDE.md)
- [客户端示例](./client_example.py)
- [README](./README.md)

---

## 🐛 故障排查

### 服务器无法启动

**检查**:
- Python 版本 >= 3.8
- 依赖已安装: `pip list | grep funasr`
- 端口未被占用: `netstat -an | grep 5002`

### 识别结果为空

**检查**:
- 音频格式正确（WAV, 16kHz, 单声道）
- 音频质量良好
- 服务器日志: `tail -f server.log`

### 连接超时

**检查**:
- 服务器地址正确
- 防火墙允许端口 5002
- 网络连接正常

---

**需要帮助？** 查看 [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) 获取详细信息。
