#!/bin/bash
# ASR Server 一键部署脚本
# 用法: bash deploy.sh [install|start|stop|restart|status|logs]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$DEPLOY_DIR/venv"
LOG_DIR="$DEPLOY_DIR/logs"
PID_FILE="$DEPLOY_DIR/asr_server.pid"
PORT=${ASR_PORT:-5002}
HOST=${ASR_HOST:-"0.0.0.0"}
WORKERS=${ASR_WORKERS:-1}  # ASR 模型占用显存大，worker 不宜过多

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &>/dev/null; then
        PYTHON_CMD="python"
    else
        error "Python not found. Install Python 3.8+"
        exit 1
    fi
    info "Python: $($PYTHON_CMD --version 2>&1)"
}

create_venv() {
    if [ -d "$VENV_DIR" ]; then
        info "venv exists, skipping"
    else
        info "Creating venv..."
        $PYTHON_CMD -m venv "$VENV_DIR"
    fi
}

activate_venv() {
    source "$VENV_DIR/bin/activate"
}

install_deps() {
    info "Installing dependencies..."
    activate_venv
    pip install --upgrade pip -q
    pip install -r "$DEPLOY_DIR/requirements.txt" -q
    info "Dependencies installed"
}

download_models() {
    info "Checking models (will auto-download on first run)..."
    activate_venv
    python -c "
from funasr import AutoModel
import os
os.environ.setdefault('MODELSCOPE_CACHE', os.path.expanduser('~/.cache/modelscope'))
print('Downloading paraformer-zh-streaming...')
AutoModel(model='paraformer-zh-streaming', device='cpu', disable_update=True)
print('Downloading fsmn-vad...')
AutoModel(model='fsmn-vad', device='cpu', disable_update=True)
print('Models ready')
" 2>&1 || warn "Model download will happen on first server start"
}

start_server() {
    info "Starting ASR server on $HOST:$PORT ..."

    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            warn "Already running (PID: $PID)"
            return
        fi
        rm -f "$PID_FILE"
    fi

    if [ ! -d "$VENV_DIR" ]; then
        error "Run 'bash deploy.sh install' first"
        exit 1
    fi

    activate_venv
    mkdir -p "$LOG_DIR"

    cd "$DEPLOY_DIR"

    # 检测 GPU
    GPU_INFO=$(python -c "import torch; print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')" 2>/dev/null || echo "CPU")
    info "Device: $GPU_INFO"

    nohup gunicorn \
        -w $WORKERS \
        -b $HOST:$PORT \
        --timeout 300 \
        --access-logfile "$LOG_DIR/access.log" \
        --error-logfile "$LOG_DIR/error.log" \
        --pid "$PID_FILE" \
        --daemon \
        server:app

    sleep 2

    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        info "Server started (PID: $PID)"
        info "URL: http://$HOST:$PORT"
        info "Health: curl http://localhost:$PORT/health"
    else
        error "Failed to start. Check: $LOG_DIR/error.log"
        exit 1
    fi
}

stop_server() {
    if [ ! -f "$PID_FILE" ]; then
        warn "Not running"
        return
    fi
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        sleep 2
        if ps -p $PID > /dev/null 2>&1; then
            kill -9 $PID
        fi
        rm -f "$PID_FILE"
        info "Server stopped"
    else
        rm -f "$PID_FILE"
    fi
}

show_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            info "Running (PID: $PID)"
            curl -s "http://localhost:$PORT/health" && echo "" || warn "Health check failed"
        else
            warn "PID file exists but process dead"
            rm -f "$PID_FILE"
        fi
    else
        warn "Not running"
    fi
}

show_logs() {
    if [ -f "$LOG_DIR/error.log" ]; then
        tail -f "$LOG_DIR/error.log"
    else
        warn "No logs yet"
    fi
}

case "${1:-}" in
    install)
        check_python
        create_venv
        install_deps
        download_models
        mkdir -p "$LOG_DIR"
        info "Done! Run: bash deploy.sh start"
        ;;
    start)   start_server ;;
    stop)    stop_server ;;
    restart) stop_server; sleep 2; start_server ;;
    status)  show_status ;;
    logs)    show_logs ;;
    *)
        echo "ASR Server Deploy Script"
        echo ""
        echo "Usage: bash deploy.sh [command]"
        echo ""
        echo "Commands:"
        echo "  install   - Install dependencies and download models"
        echo "  start     - Start server"
        echo "  stop      - Stop server"
        echo "  restart   - Restart server"
        echo "  status    - Check status"
        echo "  logs      - Tail logs"
        echo ""
        echo "Environment variables:"
        echo "  ASR_PORT=5002   Server port (default: 5002)"
        echo "  ASR_HOST=0.0.0.0 Listen address (default: 0.0.0.0)"
        echo "  ASR_WORKERS=1   Worker count (default: 1)"
        exit 1
        ;;
esac
