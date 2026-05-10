#!/bin/bash
# ============================================================
# ASR 服务器一键部署脚本（完整版）
# 支持自动检测环境、下载模型、配置服务
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 默认配置
PORT=5002
USE_GPU=false
MODEL_DIR="./models/ASR"
INSTALL_SERVICE=false
SKIP_MODEL_DOWNLOAD=false

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
        --install-service)
            INSTALL_SERVICE=true
            shift
            ;;
        --skip-models)
            SKIP_MODEL_DOWNLOAD=true
            shift
            ;;
        --help)
            echo "用法: bash one_click_deploy.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --gpu              安装 GPU 版本的 PyTorch"
            echo "  --port PORT        指定服务端口 (默认: 5002)"
            echo "  --install-service  安装为系统服务 (systemd)"
            echo "  --skip-models      跳过模型下载"
            echo "  --help             显示此帮助信息"
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            exit 1
            ;;
    esac
done

echo "============================================"
echo "  ASR 服务器一键部署"
echo "============================================"
echo ""

# 1. 检测操作系统
log_info "检测操作系统..."
OS="$(uname -s)"
case "${OS}" in
    Linux*)     MACHINE=Linux;;
    Darwin*)    MACHINE=Mac;;
    CYGWIN*)    MACHINE=Cygwin;;
    MINGW*)     MACHINE=MinGw;;
    *)          MACHINE="UNKNOWN:${OS}"
esac
log_success "操作系统: ${MACHINE}"

# 2. 检测 Python
log_info "检测 Python 环境..."
if command -v python3 &> /dev/null; then
    PYTHON=python3
    PIP=pip3
elif command -v python &> /dev/null; then
    PYTHON=python
    PIP=pip
else
    log_error "未找到 Python"
    echo "请安装 Python 3.8+ 并添加到 PATH"
    exit 1
fi

PYTHON_VERSION=$($PYTHON --version 2>&1)
log_success "Python: ${PYTHON_VERSION}"

# 3. 检测 GPU
log_info "检测 GPU..."
if [ "$USE_GPU" = true ]; then
    if command -v nvidia-smi &> /dev/null; then
        GPU_INFO=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        if [ -n "$GPU_INFO" ]; then
            log_success "GPU: ${GPU_INFO}"
        else
            log_warn "nvidia-smi 可用但未检测到 GPU，将使用 CPU"
            USE_GPU=false
        fi
    else
        log_warn "未找到 nvidia-smi，将使用 CPU"
        USE_GPU=false
    fi
else
    log_info "使用 CPU 模式"
fi

# 4. 创建目录结构
log_info "创建目录结构..."
mkdir -p "$MODEL_DIR"
mkdir -p logs
log_success "目录创建完成"

# 5. 安装 Python 依赖
log_info "安装 Python 依赖..."
$PYTHON -m pip install --upgrade pip

if [ "$USE_GPU" = true ]; then
    log_info "安装 GPU 版本 PyTorch..."
    $PIP install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
else
    log_info "安装 CPU 版本 PyTorch..."
    $PIP install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
fi

log_info "安装其他依赖..."
$PIP install -r requirements.txt
log_success "依赖安装完成"

# 6. 下载模型
if [ "$SKIP_MODEL_DOWNLOAD" = false ]; then
    log_info "下载 ASR 模型..."

    $PYTHON << 'EOF'
import os
import sys
from pathlib import Path

model_dir = Path("./models/ASR")
model_dir.mkdir(parents=True, exist_ok=True)

def download_model(model_id, local_dir):
    """下载模型（支持 ModelScope 和 HuggingFace）"""
    local_path = model_dir / local_dir
    if local_path.exists() and any(local_path.iterdir()):
        print(f"✓ {local_dir} 已存在，跳过下载")
        return True

    print(f"正在下载 {model_id}...")
    try:
        # 尝试 ModelScope
        from modelscope.hub.snapshot_download import snapshot_download
        snapshot_download(model_id, local_dir=str(local_path))
        print(f"✓ {local_dir} 下载完成")
        return True
    except Exception as e:
        print(f"ModelScope 下载失败: {e}")

    try:
        # 尝试 HuggingFace
        from huggingface_hub import snapshot_download as hf_download
        hf_download(
            repo_id=model_id.replace("iic/", "funasr/"),
            local_dir=str(local_path)
        )
        print(f"✓ {local_dir} 下载完成 (HuggingFace)")
        return True
    except Exception as e:
        print(f"HuggingFace 下载失败: {e}")

    print(f"⚠ {local_dir} 下载失败，将在首次运行时自动下载")
    return False

# 下载 Paraformer 流式模型
download_model(
    "iic/speech_paraformer-zh-streaming",
    "paraformer-zh-streaming"
)

# 下载 VAD 模型
download_model(
    "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "fsmn-vad"
)

# 下载标点恢复模型（可选）
download_model(
    "iic/punc_ct-transformer_zh-cn-common-vad_realtime-vocab272727",
    "punc_ct-transformer"
)

EOF

    log_success "模型下载完成"
else
    log_warn "跳过模型下载"
fi

# 7. 验证模型
log_info "验证模型文件..."
if [ -d "$MODEL_DIR/paraformer-zh-streaming" ] && [ -f "$MODEL_DIR/paraformer-zh-streaming/model.pt" ]; then
    log_success "✓ Paraformer 模型已就绪"
else
    log_warn "⚠ Paraformer 模型未找到，将在首次运行时自动下载"
fi

if [ -d "$MODEL_DIR/fsmn-vad" ]; then
    log_success "✓ VAD 模型已就绪"
else
    log_warn "⚠ VAD 模型未找到，将在首次运行时自动下载"
fi

# 8. 创建启动脚本
log_info "创建启动脚本..."

cat > start.sh << EOF
#!/bin/bash
# ASR 服务器启动脚本

cd "\$(dirname "\$0")"

echo "============================================"
echo "  ASR 服务器启动"
echo "============================================"
echo ""
echo "端口: $PORT"
echo "GPU: $USE_GPU"
echo "模型目录: $MODEL_DIR"
echo ""

# 设置环境变量
export FUNASR_CACHE_DIR="$MODEL_DIR"

# 启动服务器
$PYTHON server.py \\
    --host 0.0.0.0 \\
    --port $PORT \\
    $([ "$USE_GPU" = true ] && echo "--device cuda:0" || echo "--device cpu") \\
    2>&1 | tee logs/asr_server.log
EOF

chmod +x start.sh
log_success "启动脚本创建完成"

# 9. 创建停止脚本
cat > stop.sh << EOF
#!/bin/bash
# ASR 服务器停止脚本

echo "正在停止 ASR 服务器..."

# 查找并停止进程
PIDS=\$(pgrep -f "server.py.*--port $PORT")
if [ -n "\$PIDS" ]; then
    kill \$PIDS
    echo "已停止进程: \$PIDS"
else
    echo "未找到运行中的 ASR 服务器"
fi
EOF

chmod +x stop.sh

# 10. 安装 systemd 服务（可选）
if [ "$INSTALL_SERVICE" = true ] && [ "$MACHINE" = "Linux" ]; then
    log_info "安装 systemd 服务..."

    cat > asr-server.service << EOF
[Unit]
Description=ASR Server (FunASR)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
Group=$(id -gn)
WorkingDirectory=$(pwd)
Environment="PATH=$(dirname $PYTHON):$PATH"
Environment="FUNASR_CACHE_DIR=$(pwd)/models/ASR"
ExecStart=$(which $PYTHON) server.py --host 0.0.0.0 --port $PORT $([ "$USE_GPU" = true ] && echo "--device cuda:0" || echo "--device cpu")
ExecStop=/bin/kill -SIGTERM \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=asr-server

[Install]
WantedBy=multi-user.target
EOF

    echo ""
    log_info "要安装为系统服务，请执行："
    echo "  sudo cp asr-server.service /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable asr-server"
    echo "  sudo systemctl start asr-server"
    echo ""
fi

# 11. 创建健康检查脚本
cat > health_check.sh << EOF
#!/bin/bash
# 健康检查脚本

echo "检查 ASR 服务器状态..."

RESPONSE=\$(curl -s -w "\\n%{http_code}" http://localhost:$PORT/health 2>/dev/null)
HTTP_CODE=\$(echo "\$RESPONSE" | tail -1)
BODY=\$(echo "\$RESPONSE" | head -1)

if [ "\$HTTP_CODE" = "200" ]; then
    echo "✓ 服务器运行正常"
    echo "响应: \$BODY"
    exit 0
else
    echo "✗ 服务器异常 (HTTP \$HTTP_CODE)"
    exit 1
fi
EOF

chmod +x health_check.sh

# 12. 创建测试脚本
cat > test_recognize.sh << EOF
#!/bin/bash
# 测试语音识别

if [ -z "\$1" ]; then
    echo "用法: bash test_recognize.sh <音频文件>"
    echo "示例: bash test_recognize.sh test.wav"
    exit 1
fi

AUDIO_FILE="\$1"
if [ ! -f "\$AUDIO_FILE" ]; then
    echo "错误: 文件不存在 - \$AUDIO_FILE"
    exit 1
fi

echo "正在识别: \$AUDIO_FILE"
AUDIO_B64=\$(base64 -w 0 "\$AUDIO_FILE" 2>/dev/null || base64 -i "\$AUDIO_FILE")

RESPONSE=\$(curl -s -X POST http://localhost:$PORT/asr/recognize \\
    -H "Content-Type: application/json" \\
    -d "{\\"audio\\": \\"\$AUDIO_B64\\"}")

echo "识别结果:"
echo "\$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "\$RESPONSE"
EOF

chmod +x test_recognize.sh

echo ""
echo "============================================"
log_success "部署完成！"
echo "============================================"
echo ""
echo "📁 目录结构:"
echo "  ├── server.py           # 服务器主程序"
echo "  ├── requirements.txt    # Python 依赖"
echo "  ├── models/ASR/         # 模型目录"
echo "  ├── start.sh            # 启动脚本"
echo "  ├── stop.sh             # 停止脚本"
echo "  ├── health_check.sh     # 健康检查"
echo "  └── test_recognize.sh   # 测试脚本"
echo ""
echo "🚀 快速启动:"
echo "  bash start.sh"
echo ""
echo "🧪 验证服务:"
echo "  bash health_check.sh"
echo ""
echo "🎤 测试识别:"
echo "  bash test_recognize.sh test.wav"
echo ""
echo "📊 查看日志:"
echo "  tail -f logs/asr_server.log"
echo ""

if [ "$INSTALL_SERVICE" = true ]; then
    echo "🔧 系统服务:"
    echo "  sudo cp asr-server.service /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable asr-server"
    echo "  sudo systemctl start asr-server"
    echo ""
fi

echo "📚 更多信息请查看 DEPLOYMENT_GUIDE.md"
echo ""
