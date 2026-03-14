# CosyVoice TensorRT 加速新手完整教程（一步一步）

适用场景：你是初学者，希望在这台 Linux 服务器上把 CosyVoice 的 TensorRT 加速从 0 开启到可用。  
当前项目目录：`/root/autodl-tmp/tts_server`

---

## 0. 你将完成什么

做完本教程后，你会得到：
1. 已安装可用的 TensorRT Python 包
2. 在模型目录中生成 TRT 引擎文件（`.mygpu.plan`）
3. 启动服务并实际启用 TRT
4. 能通过日志确认“TensorRT 已启用”

---

## 1. 先理解一个关键点（非常重要）

在你这个项目里，**开启 TRT 需要同时满足两件事**：

- 条件 A：设置环境变量 `COSYVOICE_USE_TRT=1`
- 条件 B：模型目录里存在 TRT 引擎文件：
  - `flow.decoder.estimator.fp16.mygpu.plan` 或
  - `flow.decoder.estimator.fp32.mygpu.plan`

只做 A 不做 B，不会启用 TRT。

---

## 2. 打开终端并进入项目目录

```bash
cd /root/autodl-tmp/tts_server
```

后续命令都默认在这个目录执行。

---

## 3. 第一步：检查基础环境是否正常

### 3.1 检查 GPU

```bash
nvidia-smi
```

你应该能看到 GPU 型号（例如 4090）、Driver Version、CUDA Version。  
如果命令报错，说明 NVIDIA 驱动/容器 GPU 挂载有问题，需要先修这个。

### 3.2 检查 Python 与 PyTorch CUDA

```bash
python - <<'PY'
import torch
print('torch:', torch.__version__)
print('torch cuda:', torch.version.cuda)
print('cuda available:', torch.cuda.is_available())
if torch.cuda.is_available():
    print('gpu:', torch.cuda.get_device_name(0))
PY
```

期望：`cuda available: True`。

---

## 4. 第二步：检查模型文件是否齐全

### 4.1 查看 CosyVoice 模型目录

```bash
ls -lh models/TTS/CosyVoice2-0.5B | sed -n '1,200p'
```

至少要看到（通常已存在）：
- `flow.decoder.estimator.fp32.onnx`
- `campplus.onnx`
- `speech_tokenizer_v2.onnx`

### 4.2 检查是否已有 `.plan`

```bash
ls -lh models/TTS/CosyVoice2-0.5B/flow.decoder.estimator.*.mygpu.plan
```

- 如果看到了 `.mygpu.plan`，可跳到第 6 步（直接启用 TRT）。
- 如果提示没有该文件，继续第 5 步生成。

---

## 5. 第三步：安装 TensorRT 并生成 `.plan`

> 新手建议按顺序执行，不要跳。

### 5.1 升级打包工具

```bash
python -m pip install -U pip setuptools wheel
```

### 5.2 安装 TensorRT（CUDA 12 变体）

```bash
python -m pip install tensorrt-cu12==10.15.1.29 --extra-index-url https://pypi.nvidia.com
```

### 5.3 验证 TensorRT 已可导入

```bash
python - <<'PY'
import tensorrt as trt
print('TensorRT version:', trt.__version__)
PY
```

如果这里报 `No module named 'tensorrt'`，通常是：
- 你在 A Python 安装，但在 B Python 运行。  
请用同一个 `python` 路径执行安装和验证。

### 5.4 生成 FP16 的 TRT engine（推荐）

```bash
python - <<'PY'
from cosyvoice.cli.cosyvoice import CosyVoice2
model_dir = 'models/TTS/CosyVoice2-0.5B'
_ = CosyVoice2(model_dir=model_dir, load_jit=False, load_trt=True, fp16=True, trt_concurrent=1)
print('TRT engine build done')
PY
```

这一步会自动把 ONNX 转为 TRT engine（`.mygpu.plan`）。

### 5.5 确认 `.plan` 已生成

```bash
ls -lh models/TTS/CosyVoice2-0.5B/flow.decoder.estimator.*.mygpu.plan
```

看到文件就表示生成成功。

---

## 6. 第四步：正式启用 TRT 启动服务

### 6.1 设置环境变量

```bash
export COSYVOICE_MODEL_PATH=/root/autodl-tmp/tts_server/models/TTS/CosyVoice2-0.5B
export COSYVOICE_USE_TRT=1
```

### 6.2 前台启动（先用这个，便于看日志）

```bash
python service.py --host 0.0.0.0 --port 5001
```

启动日志里应出现类似信息：
- `TTS 引擎初始化成功 (TensorRT 已启用)`
- 或 `加载模型中... (JIT: 禁用, TRT: 启用, FP16: 启用)`

如果没看到 TRT 启用，回到第 5.5 步检查 `.plan` 是否真存在。

---

## 7. 第五步：验证服务工作正常

新开一个终端，执行：

### 7.1 健康检查

```bash
curl http://127.0.0.1:5001/health
```

### 7.2 发起一次合成

```bash
curl -X POST http://127.0.0.1:5001/tts/generate \
  -H "Content-Type: application/json" \
  -d '{"text":"你好，这是 TensorRT 加速测试"}' \
  -o /tmp/tts_resp.json
```

如果返回正常，说明服务与推理链路都通了。

---

## 8. 第六步：改成后台运行（可选）

```bash
cd /root/autodl-tmp/tts_server
export COSYVOICE_MODEL_PATH=/root/autodl-tmp/tts_server/models/TTS/CosyVoice2-0.5B
export COSYVOICE_USE_TRT=1
nohup python service.py --host 0.0.0.0 --port 5001 > tts.log 2>&1 &
```

查看日志：

```bash
tail -f tts.log
```

---

## 9. 常见问题（新手最容易遇到）

### 问题 1：`No module named 'tensorrt'`
原因：环境不一致。  
处理：确认 `which python`，并用该 Python 安装：

```bash
which python
python -m pip install tensorrt-cu12==10.15.1.29 --extra-index-url https://pypi.nvidia.com
```

### 问题 2：生成 `.plan` 失败
可能原因：
- TensorRT 未正确安装
- ONNX 文件缺失
- 显存/资源不足

处理：
1) 先确认 `import tensorrt` 成功  
2) 确认 `flow.decoder.estimator.fp32.onnx` 存在  
3) 保持 `trt_concurrent=1`，优先 `fp16=True`

### 问题 3：设置了 `COSYVOICE_USE_TRT=1` 仍未启用
原因：没有 `.mygpu.plan`。  
处理：回到第 5 步重新生成。

### 问题 4：换机器后 `.plan` 不可用
`.plan` 对平台/硬件敏感。  
处理：在新机器上重新生成，不要直接复用旧 plan。

---

## 10. 一键最短流程（熟悉后使用）

```bash
cd /root/autodl-tmp/tts_server
python -m pip install -U pip setuptools wheel
python -m pip install tensorrt-cu12==10.15.1.29 --extra-index-url https://pypi.nvidia.com
python - <<'PY'
from cosyvoice.cli.cosyvoice import CosyVoice2
_ = CosyVoice2('models/TTS/CosyVoice2-0.5B', load_jit=False, load_trt=True, fp16=True, trt_concurrent=1)
print('plan done')
PY
export COSYVOICE_MODEL_PATH=/root/autodl-tmp/tts_server/models/TTS/CosyVoice2-0.5B
export COSYVOICE_USE_TRT=1
python service.py --host 0.0.0.0 --port 5001
```

---

## 11. 给初学者的操作建议

- 每执行完一步，先看输出是否符合预期，再做下一步。
- 不要同时开太多终端改环境变量，容易混乱。
- 先前台跑通，再切后台。
- 如果你愿意，我可以继续帮你“逐条执行并检查输出”，你只需要回复：`开始第1步`。