#!/bin/bash
# ASR 服务器一键部署脚本 (Linux/macOS)
# 用法: bash deploy.sh [install|start|stop|restart|status]

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_DIR="$PROJECT_ROOT/deploy/asr_server"
VENV_DIR="$DEPLOY_DIR/venv"
LOG_DIR="$DEPLOY_DIR/logs"
PID_FILE="$DEPLOY_DIR/asr_server.pid"
LOG_FILE="$LOG_DIR/asr_server.log"
PORT=5002
HOST="0.0.0.0"
WORKERS=4

# 打印信息
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查 Python 版本
check_python() {
    info "检查 Python 版本..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        error "未找到 Python，请先安装 Python 3.8+"
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    info "Python 版本: $PYTHON_VERSION"
    
    # 检查版本是否 >= 3.8
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 8 ]); then
        error "Python 版本过低，需要 3.8+，当前版本: $PYTHON_VERSION"
        exit 1
    fi
}

# 创建虚拟环境
create_venv() {
    info "创建虚拟环境..."
    
    if [ -d "$VENV_DIR" ]; then
        warn "虚拟环境已存在，跳过创建"
    else
        $PYTHON_CMD -m venv "$VENV_DIR"
        info "虚拟环境创建完成: $VENV_DIR"
    fi
}

# 激活虚拟环境
activate_venv() {
    source "$VENV_DIR/bin/activate"
}

# 安装依赖
install_dependencies() {
    info "安装依赖..."
    
    activate_venv
    
    # 升级 pip
    pip install --upgrade pip
    
    # 安装依赖
    if [ -f "$DEPLOY_DIR/requirements.txt" ]; then
        pip install -r "$DEPLOY_DIR/requirements.txt"
    else
        # 基础依赖
        pip install flask gunicorn requests numpy
        
        # FunASR 和 PyTorch
        pip install funasr torch torchaudio
        
        # 其他依赖
        pip install sounddevice librosa
    fi
    
    info "依赖安装完成"
}

# 检查模型
check_models() {
    info "检查模型..."
    
    MODEL_DIR="$PROJECT_ROOT/models/ASR"
    
    if [ ! -d "$MODEL_DIR/paraformer-zh-streaming" ]; then
        warn "未找到 Paraformer 模型，首次运行时将自动下载"
    else
        info "Paraformer 模型已存在"
    fi
    
    if [ ! -d "$MODEL_DIR/fsmn-vad" ]; then
        warn "未找到 VAD 模型，首次运行时将自动下载"
    else
        info "VAD 模型已存在"
    fi
}

# 创建日志目录
create_log_dir() {
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR"
        info "创建日志目录: $LOG_DIR"
    fi
}

# 安装
install() {
    info "开始安装 ASR 服务器..."
    echo "================================"
    
    check_python
    create_venv
    install_dependencies
    check_models
    create_log_dir
    
    echo "================================"
    info "安装完成！"
    info "使用 'bash deploy.sh start' 启动服务器"
}

# 启动服务器
start() {
    info "启动 ASR 服务器..."
    
    # 检查是否已经在运行
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            warn "服务器已在运行 (PID: $PID)"
            return
        else
            warn "PID 文件存在但进程不存在，清理 PID 文件"
            rm -f "$PID_FILE"
        fi
    fi
    
    # 检查虚拟环境
    if [ ! -d "$VENV_DIR" ]; then
        error "虚拟环境不存在，请先运行: bash deploy.sh install"
        exit 1
    fi
    
    activate_venv
    
    # 启动服务器
    cd "$DEPLOY_DIR"
    
    info "启动 Gunicorn..."
    info "监听地址: $HOST:$PORT"
    info "Worker 数量: $WORKERS"
    info "日志文件: $LOG_FILE"
    
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
        info "服务器已启动 (PID: $PID)"
        info "访问地址: http://$HOST:$PORT"
        info "健康检查: curl http://localhost:$PORT/health"
    else
        error "服务器启动失败，请查看日志: $LOG_DIR/error.log"
        exit 1
    fi
}

# 停止服务器
stop() {
    info "停止 ASR 服务器..."
    
    if [ ! -f "$PID_FILE" ]; then
        warn "PID 文件不存在，服务器可能未运行"
        return
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        sleep 2
        
        # 强制杀死
        if ps -p $PID > /dev/null 2>&1; then
            warn "进程未响应，强制杀死"
            kill -9 $PID
        fi
        
        rm -f "$PID_FILE"
        info "服务器已停止"
    else
        warn "进程不存在 (PID: $PID)"
        rm -f "$PID_FILE"
    fi
}

# 重启服务器
restart() {
    info "重启 ASR 服务器..."
    stop
    sleep 2
    start
}

# 查看状态
status() {
    info "检查 ASR 服务器状态..."
    
    if [ ! -f "$PID_FILE" ]; then
        warn "服务器未运行（PID 文件不存在）"
        return
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ps -p $PID > /dev/null 2>&1; then
        info "服务器正在运行 (PID: $PID)"
        
        # 检查端口
        if command -v netstat &> /dev/null; then
            if netstat -tuln | grep ":$PORT " > /dev/null; then
                info "端口 $PORT 正在监听"
            else
                warn "端口 $PORT 未监听"
            fi
        fi
        
        # 健康检查
        if command -v curl &> /dev/null; then
            info "执行健康检查..."
            if curl -s "http://localhost:$PORT/health" > /dev/null; then
                info "健康检查通过 ✓"
            else
                warn "健康检查失败 ✗"
            fi
        fi
    else
        warn "服务器未运行（进程不存在）"
        rm -f "$PID_FILE"
    fi
}

# 查看日志
logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    elif [ -f "$LOG_DIR/error.log" ]; then
        tail -f "$LOG_DIR/error.log"
    else
        warn "日志文件不存在"
    fi
}

# 主函数
main() {
    case "${1:-}" in
        install)
            install
            ;;
        start)
            start
            ;;
        stop)
            stop
            ;;
        restart)
            restart
            ;;
        status)
            status
            ;;
        logs)
            logs
            ;;
        *)
            echo "ASR 服务器部署脚本"
            echo ""
            echo "用法: bash deploy.sh [命令]"
            echo ""
            echo "命令:"
            echo "  install   - 安装依赖和配置环境"
            echo "  start     - 启动服务器"
            echo "  stop      - 停止服务器"
            echo "  restart   - 重启服务器"
            echo "  status    - 查看服务器状态"
            echo "  logs      - 查看日志（实时）"
            echo ""
            echo "示例:"
            echo "  bash deploy.sh install   # 首次安装"
            echo "  bash deploy.sh start     # 启动服务器"
            echo "  bash deploy.sh status    # 查看状态"
            exit 1
            ;;
    esac
}

main "$@"
