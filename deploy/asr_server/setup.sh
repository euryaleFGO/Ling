#!/bin/bash
# ============================================================
# ASR 服务器一键部署脚本
# 用法: bash setup.sh [--gpu] [--port 5002]
# ============================================================

set -e

# 默认配置
PORT=5002
USE_GPU=false
MODEL_DIR="./models/ASR"

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --gpu)
            USE_GPU=true
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --help)
            echo "用法: bash setup.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --gpu       安装 GPU 版本的 PyTorch"
            echo "  --port PORT 指定服务端口 (默认: 5002)"
            echo "  --help      显示此帮助信息"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

echo "============================================"
echo "  ASR 服务器一键部署"
echo "============================================"
echo ""

# 1. 检查 Python 版本
echo "[1/5] 检查 Python 环境..."
python3 --version || {
    echo "错误: 未找到 python3"
    exit 1
}

# 2. 安装 Python 依赖
echo "[2/5] 安装 Python 依赖..."
pip3 install --upgrade pip

if [ "$USE_GPU" = true ]; then
    echo "安装 GPU 版本 PyTorch..."
    pip3 install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
else
    echo "安装 CPU 版本 PyTorch..."
    pip3 install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
fi

pip3 install -r requirements.txt

# 3. 下载模型
echo "[3/5] 下载 ASR 模型..."
mkdir -p "$MODEL_DIR"

# 使用 Python 下载模型（ModelScope 或 FunASR 自动下载）
python3 << 'EOF'
import os
from pathlib import Path

model_dir = Path("./models/ASR")
model_dir.mkdir(parents=True, exist_ok=True)

print("正在下载 Paraformer 流式模型...")
try:
    from modelscope.hub.snapshot_download import snapshot_download as ms_download
    # ModelScope 下载
    ms_download(
        "iic/speech_paraformer-zh-streaming",
        local_dir=str(model_dir / "paraformer-zh-streaming")
    )
    print("Paraformer 模型下载完成")
except Exception as e:
    print(f"ModelScope 下载失败: {e}")
    print("尝试使用 FunASR 自动下载...")
    # FunASR 会在首次使用时自动下载

print("正在下载 VAD 模型...")
try:
    from modelscope.hub.snapshot_download import snapshot_download as ms_download
    ms_download(
        "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        local_dir=str(model_dir / "fsmn-vad")
    )
    print("VAD 模型下载完成")
except Exception as e:
    print(f"VAD 模型下载失败: {e}")
    print("VAD 模型将在首次使用时自动下载")

EOF

# 4. 验证模型
echo "[4/5] 验证模型文件..."
if [ -d "$MODEL_DIR/paraformer-zh-streaming" ]; then
    echo "✓ Paraformer 模型已就绪"
else
    echo "⚠ Paraformer 模型未找到，将在首次运行时自动下载"
fi

if [ -d "$MODEL_DIR/fsmn-vad" ]; then
    echo "✓ VAD 模型已就绪"
else
    echo "⚠ VAD 模型未找到，将在首次运行时自动下载"
fi

# 5. 创建启动脚本
echo "[5/5] 创建启动脚本..."

cat > start.sh << EOF
#!/bin/bash
# ASR 服务器启动脚本

echo "启动 ASR 服务器..."
echo "端口: $PORT"
echo "GPU: $USE_GPU"
echo ""

python3 server.py \\
    --host 0.0.0.0 \\
    --port $PORT \\
    $([ "$USE_GPU" = true ] && echo "--device cuda:0" || echo "--device cpu")
EOF

chmod +x start.sh

# 创建 systemd 服务文件（可选）
cat > asr-server.service << EOF
[Unit]
Description=ASR Server
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
Environment="PATH=$(which python3 | xargs dirname)/.."
ExecStart=$(which python3) server.py --host 0.0.0.0 --port $PORT $([ "$USE_GPU" = true ] && echo "--device cuda:0" || echo "--device cpu")
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "============================================"
echo "  部署完成！"
echo "============================================"
echo ""
echo "启动服务:"
echo "  bash start.sh"
echo ""
echo "或使用 systemd (推荐生产环境):"
echo "  sudo cp asr-server.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable asr-server"
echo "  sudo systemctl start asr-server"
echo ""
echo "验证服务:"
echo "  curl http://localhost:$PORT/health"
echo ""
echo "查看日志:"
echo "  sudo journalctl -u asr-server -f"
echo ""
