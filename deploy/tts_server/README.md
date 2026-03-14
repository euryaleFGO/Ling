# TTS 云端服务部署指南

## 快速部署

### 1. 上传文件到服务器

```bash
# 本地打包后上传
scp -P 46898 tts_server.zip root@connect.cqa1.seetacloud.com:~/
```

### 2. 服务器上解压并安装

```bash
# 解压
cd ~
unzip tts_server.zip
cd tts_server

# 安装依赖
pip install -r requirements.txt

# 安装 PyTorch (CUDA 版本)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 3. 下载模型

```bash
# 创建模型目录
mkdir -p models/TTS

# 从 ModelScope 下载 CosyVoice2-0.5B
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('iic/CosyVoice2-0.5B', local_dir='models/TTS/CosyVoice2-0.5B')"
```

### 4. 启动服务

```bash
# 前台运行（测试用）
python service.py --host 0.0.0.0 --port 5001

# 后台运行（生产用）
nohup python service.py --host 0.0.0.0 --port 5001 > tts.log 2>&1 &

# 或使用 screen
screen -S tts
python service.py --host 0.0.0.0 --port 5001
# Ctrl+A, D 退出 screen
```

### 5. 测试服务

```bash
# 健康检查
curl http://localhost:5001/health

# 测试生成
curl -X POST http://localhost:5001/tts/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，这是测试"}'
```

---

## 本地调用服务器（从你电脑发请求）

服务在服务器上启动后，有两种方式从**本地电脑**发请求并拿到生成的音频。

### 方式一：直接访问服务器 IP（需开放端口）

1. **确认服务器 5001 端口已开放**  
   在云控制台/防火墙里放行 5001（或你使用的端口）。

2. **本地用 curl 测试**（把 `你的服务器IP` 换成实际 IP 或域名，如 `connect.cqa1.seetacloud.com`）：
   ```bash
   # 健康检查
   curl http://你的服务器IP:5001/health

   # 生成音频（返回 JSON，内含 base64 音频）
   curl -X POST http://你的服务器IP:5001/tts/generate \
     -H "Content-Type: application/json" \
     -d '{"text": "你好，这是测试"}' \
     -o response.json
   ```
   再从 `response.json` 里取出 `audio` 字段做 base64 解码即可得到 WAV。

3. **或用提供的 Python 客户端**  
   把 `client_example.py` 拷到本地，修改里面的 `SERVER_URL`：
   ```python
   SERVER_URL = "http://你的服务器IP:5001"
   ```
   然后安装依赖并运行：
   ```bash
   pip install requests
   python client_example.py "你好，这是测试"
   ```
   会在当前目录生成 `output.wav`。

### 方式二：SSH 端口转发（不开放 5001 时推荐）

在**本地**执行一次（保持该终端不关）：

```bash
ssh -L 5001:localhost:5001 -P 46898 root@connect.cqa1.seetacloud.com
```

或只做端口转发（不登录 shell）：

```bash
ssh -L 5001:localhost:5001 -P 46898 -N root@connect.cqa1.seetacloud.com
```

之后在本地把服务当成 `127.0.0.1:5001` 用即可：

```bash
curl http://127.0.0.1:5001/health
python client_example.py "你好，这是测试"
```

`client_example.py` 里默认就是 `SERVER_URL = "http://127.0.0.1:5001"`，无需改。

---

## API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/tts/generate` | POST | 同步生成音频 |
| `/tts/generate/stream` | POST | **流式生成**：按句/段边合成边返回（SSE） |
| `/tts/enqueue` | POST | 异步入队 |
| `/tts/dequeue` | GET | 获取音频段 |
| `/tts/speakers` | GET | 列出说话人 |
| `/tts/add_speaker` | POST | 添加说话人 |

### 生成音频示例

```python
import requests
import base64

resp = requests.post("http://服务器IP:5001/tts/generate", json={
    "text": "你好，我是AI助手",
    "use_clone": True
})

data = resp.json()
audio_bytes = base64.b64decode(data["audio"])

with open("output.wav", "wb") as f:
    f.write(audio_bytes)
```

---

### 流式生成示例（SSE）

`POST /tts/generate/stream` 按句/段边合成边返回，适合首字延迟敏感场景：

```python
import requests
import json
import base64

resp = requests.post(
    "http://服务器IP:5001/tts/generate/stream",
    json={"text": "你好，这是流式测试。一段一段返回。"},
    stream=True
)
for line in resp.iter_lines(decode_unicode=True):
    if line.startswith("data: "):
        d = json.loads(line[6:])
        if "wav_base64" in d:
            chunk = base64.b64decode(d["wav_base64"])
            # 可边收边写或边播
            print("segment", d["idx"], "/", d["total"])
```

---

## 配置说明

通过环境变量配置：

```bash
export COSYVOICE_MODEL_PATH=/path/to/CosyVoice2-0.5B
export COSYVOICE_REF_AUDIO=/path/to/reference.wav
```

### TensorRT 加速（可选）

模型目录下若已放置 TensorRT 引擎文件（如 `flow.decoder.estimator.fp16.mygpu.plan` 或 `flow.decoder.estimator.fp32.mygpu.plan`），可开启 TRT 加速：

```bash
export COSYVOICE_USE_TRT=1
```

未设置或未找到 `.mygpu.plan` 时，将使用 PyTorch 推理。

---

## 常见问题

### Q: CUDA 内存不足
A: 确保 GPU 显存 >= 4GB，或尝试减少并发请求

### Q: 模型加载慢
A: 首次加载需要下载依赖，后续会快很多

### Q: 连接被拒绝
A: 检查防火墙是否开放 5001 端口
