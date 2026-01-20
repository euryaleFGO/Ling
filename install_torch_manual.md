# PyTorch 手动下载安装指南

## 您的配置
- **显卡**: NVIDIA GeForce RTX 2050 (4GB)
- **CUDA**: 12.4
- **Python**: 3.12
- **操作系统**: Windows

## 方式 1: 使用 pip 命令（带加速参数）

```bash
# CUDA 12.1 版本（推荐，兼容性更好）
pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121 --no-cache-dir

# 或 CUDA 12.4 版本（最新）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 --no-cache-dir
```

**加速选项**:
- 添加 `--no-cache-dir`: 不缓存，节省空间
- 使用国内镜像（如果可用）:
  ```bash
  pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 -i https://pypi.tuna.tsinghua.edu.cn/simple --index-url https://download.pytorch.org/whl/cu121
  ```

## 方式 2: 手动下载 wheel 文件

### CUDA 12.1 版本（推荐）

访问 PyTorch 官方下载页面：
https://download.pytorch.org/whl/torch_stable.html

或直接下载链接（Python 3.12, CUDA 12.1, Windows）:
- **torch**: 
  - https://download.pytorch.org/whl/cu121/torch-2.3.1%2Bcu121-cp312-cp312-win_amd64.whl
- **torchvision**:
  - https://download.pytorch.org/whl/cu121/torchvision-0.18.1%2Bcu121-cp312-cp312-win_amd64.whl
- **torchaudio**:
  - https://download.pytorch.org/whl/cu121/torchaudio-2.3.1%2Bcu121-cp312-cp312-win_amd64.whl

### CUDA 12.4 版本

访问：
https://download.pytorch.org/whl/cu124/torch_stable.html

查找对应的文件（文件名包含 `cp312`, `cu124`, `win_amd64`）

### 下载后安装

```bash
# 下载完成后，在下载目录执行：
pip install torch-2.3.1+cu121-cp312-cp312-win_amd64.whl
pip install torchvision-0.18.1+cu121-cp312-cp312-win_amd64.whl
pip install torchaudio-2.3.1+cu121-cp312-cp312-win_amd64.whl
```

## 方式 3: 使用 conda 安装（如果 pip 太慢）

```bash
# 添加 PyTorch 的 conda channel
conda install pytorch torchvision torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia
```

## 验证安装

安装完成后，运行测试：

```python
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda if torch.cuda.is_available() else \"N/A\"}')"
```

或运行我们的测试文件：
```bash
python test_tts.py
```

## 推荐方案

对于您的情况（Windows + CUDA 12.4 + Python 3.12），**推荐使用 CUDA 12.1 版本的 PyTorch**，因为：
1. 兼容性更好
2. 文档和社区支持更完善
3. 版本 2.3.1 经过充分测试

如果 CUDA 12.1 版本无法正常工作，再尝试 CUDA 12.4 版本。

