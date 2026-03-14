# CosyVoice TensorRT 加速开启教程（基于当前机器现状）

更新时间：2026-02-25

## 1) 当前设备与配置现状（已核查）

### 硬件 / 驱动
- GPU：NVIDIA GeForce RTX 4090（24GB）
- Driver：560.35.03
- 驱动报告 CUDA Version：12.6

### Python / 推理依赖
- Python：3.10.8
- PyTorch：2.2.2+cu118
- `torch.cuda.is_available()`：`True`
- ONNX Runtime：`onnxruntime-gpu==1.16.0`（已安装）
- TensorRT Python 包：**未安装**（`No module named 'tensorrt'`）

### 模型目录文件（`models/TTS/CosyVoice2-0.5B`）
已存在：
- `campplus.onnx`
- `speech_tokenizer_v2.onnx`
- `flow.decoder.estimator.fp32.onnx`

缺失（TRT 加速必须）：
- `flow.decoder.estimator.fp16.mygpu.plan` 或
- `flow.decoder.estimator.fp32.mygpu.plan`

### 环境变量现状
当前未设置 `COSYVOICE_USE_TRT` / `COSYVOICE_MODEL_PATH` 等相关变量。

---

## 2) 你当前为什么还没启用 TRT

你的服务逻辑里，只有在同时满足下面两点才会启用 TRT：
1. `COSYVOICE_USE_TRT=1`
2. 模型目录里已存在 `*.mygpu.plan`

因此**仅设置环境变量还不够**。你需要先在本机生成 `.mygpu.plan` 文件。

---

## 3) 一次性开启 TensorRT 的完整步骤

以下命令默认在项目根目录执行：`/root/autodl-tmp/tts_server`

### Step A. 安装 TensorRT Python 包

```bash
cd /root/autodl-tmp/tts_server
python -m pip install -U pip setuptools wheel
python -m pip install --extra-index-url https://pypi.nvidia.com tensorrt-cu12
```

安装后验证：

```bash
python - <<'PY'
import tensorrt as trt
print('TensorRT:', trt.__version__)
PY
```

---

### Step B. 预生成 CosyVoice 的 TRT 引擎（.plan）

> 说明：这里直接调用 CosyVoice2 的 `load_trt=True`，会在本地把 ONNX 转成 TRT 引擎。

```bash
cd /root/autodl-tmp/tts_server
python - <<'PY'
from cosyvoice.cli.cosyvoice import CosyVoice2
model_dir = 'models/TTS/CosyVoice2-0.5B'
_ = CosyVoice2(model_dir=model_dir, load_jit=False, load_trt=True, fp16=True, trt_concurrent=1)
print('TRT build done')
PY
```

确认文件已生成：

```bash
ls -lh models/TTS/CosyVoice2-0.5B/flow.decoder.estimator.*.mygpu.plan
```

如果你希望生成 FP32 引擎，把上面脚本中的 `fp16=True` 改成 `fp16=False`。

---

### Step C. 设置环境变量并启动服务

```bash
cd /root/autodl-tmp/tts_server
export COSYVOICE_MODEL_PATH=/root/autodl-tmp/tts_server/models/TTS/CosyVoice2-0.5B
export COSYVOICE_USE_TRT=1
python service.py --host 0.0.0.0 --port 5001
```

或后台：

```bash
cd /root/autodl-tmp/tts_server
export COSYVOICE_MODEL_PATH=/root/autodl-tmp/tts_server/models/TTS/CosyVoice2-0.5B
export COSYVOICE_USE_TRT=1
nohup python service.py --host 0.0.0.0 --port 5001 > tts.log 2>&1 &
```

---

### Step D. 验证是否真的启用了 TRT

看日志中应出现类似：
- `TTS 引擎初始化成功 (TensorRT 已启用)`
- 或 `加载模型中... (JIT: 禁用, TRT: 启用, FP16: 启用)`

快速检查：

```bash
curl http://127.0.0.1:5001/health
```

并发起一次生成请求后观察 `tts.log`。

---

## 4) 常见报错与处理

### 1. `No module named 'tensorrt'`
TensorRT Python 包未安装到当前 Python。请用同一个 `python` 执行安装和启动。

### 2. `failed to load trt` / 反序列化失败
通常是引擎与当前环境不匹配。删除旧 plan，在当前机器重新生成：

```bash
rm -f models/TTS/CosyVoice2-0.5B/flow.decoder.estimator.*.mygpu.plan
```

然后重新执行 Step B。

### 3. 显存不足
降低并发，确保 `trt_concurrent=1`，并先使用 `fp16=True`。

---

## 5) 最短路径（你这台机器建议）

1. 安装 `tensorrt-cu12`
2. 运行 Step B 生成 `fp16.mygpu.plan`
3. `export COSYVOICE_USE_TRT=1` 后启动服务
4. 看日志确认 `TensorRT 已启用`

这样即可完成 CosyVoice TensorRT 加速。