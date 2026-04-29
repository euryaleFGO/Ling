#!/bin/bash
# 玲 (Liying) - 智能虚拟助手系统
# 一键部署脚本 (Linux/macOS)
# 用法: bash deploy.sh [install|start|stop|restart|status|logs|clean]

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/venv"
LOG_DIR="$PROJECT_ROOT/logs"
PID_DIR="$PROJECT_ROOT/.pids"
MODELS_DIR="$PROJECT_ROOT/models"
DATA_DIR="$PROJECT_ROOT/data"

# PID 文件
MONGODB_PID="$PID_DIR/mongodb.pid"
MAIN_PID="$PID_DIR/main.pid"

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

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# 打印标题
print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  玲 (Liying) - 智能虚拟助手系统${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# 检查命令是否存在
command_exists() {
    command -v "$1" &> /dev/null
}

# 检查 Python 版本
check_python() {
    info "检查 Python 版本..."
    
    if command_exists python3; then
        PYTHON_CMD="python3"
    elif command_exists python; then
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
    
    success "Python 版本检查通过"
}

# 检查 Java 版本
check_java() {
    info "检查 Java 版本..."
    
    if ! command_exists java; then
        warn "未找到 Java，Live2D 功能将无法使用"
        warn "请安装 Java 17+ 以启用 Live2D 功能"
        return 1
    fi
    
    JAVA_VERSION=$(java -version 2>&1 | head -n 1 | awk -F '"' '{print $2}')
    info "Java 版本: $JAVA_VERSION"
    
    # 检查版本是否 >= 17
    MAJOR=$(echo $JAVA_VERSION | cut -d. -f1)
    if [ "$MAJOR" -lt 17 ]; then
        warn "Java 版本过低，需要 17+，当前版本: $JAVA_VERSION"
        warn "Live2D 功能可能无法正常工作"
        return 1
    fi
    
    success "Java 版本检查通过"
    return 0
}

# 检查 Maven
check_maven() {
    info "检查 Maven..."
    
    if ! command_exists mvn; then
        warn "未找到 Maven，将使用预编译的 JAR 文件"
        return 1
    fi
    
    MVN_VERSION=$(mvn -version 2>&1 | head -n 1 | awk '{print $3}')
    info "Maven 版本: $MVN_VERSION"
    success "Maven 检查通过"
    return 0
}

# 检查 MongoDB
check_mongodb() {
    info "检查 MongoDB..."
    
    if ! command_exists mongod; then
        warn "未找到 MongoDB，请手动安装 MongoDB"
        warn "Ubuntu/Debian: sudo apt-get install mongodb"
        warn "macOS: brew install mongodb-community"
        warn "或使用 Docker: docker run -d -p 27017:27017 --name mongodb mongo:latest"
        return 1
    fi
    
    MONGO_VERSION=$(mongod --version 2>&1 | head -n 1 | awk '{print $3}')
    info "MongoDB 版本: $MONGO_VERSION"
    success "MongoDB 检查通过"
    return 0
}

# 创建必要的目录
create_directories() {
    info "创建必要的目录..."
    
    mkdir -p "$LOG_DIR"
    mkdir -p "$PID_DIR"
    mkdir -p "$MODELS_DIR"
    mkdir -p "$DATA_DIR"
    mkdir -p "$DATA_DIR/chroma_data"
    mkdir -p "$DATA_DIR/dreams"
    mkdir -p "$DATA_DIR/screenshots"
    mkdir -p "$DATA_DIR/camera"
    mkdir -p "$DATA_DIR/txt"
    
    success "目录创建完成"
}

# 创建虚拟环境
create_venv() {
    info "创建 Python 虚拟环境..."
    
    if [ -d "$VENV_DIR" ]; then
        warn "虚拟环境已存在，跳过创建"
    else
        $PYTHON_CMD -m venv "$VENV_DIR"
        success "虚拟环境创建完成: $VENV_DIR"
    fi
}

# 激活虚拟环境
activate_venv() {
    source "$VENV_DIR/bin/activate"
}

# 安装 Python 依赖
install_python_dependencies() {
    info "安装 Python 依赖..."
    
    activate_venv
    
    # 升级 pip
    pip install --upgrade pip
    
    # 安装 PyTorch (CUDA 12.1)
    info "安装 PyTorch (CUDA 12.1)..."
    pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121
    
    # 安装其他依赖
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        info "安装项目依赖..."
        pip install -r "$PROJECT_ROOT/requirements.txt"
    else
        error "未找到 requirements.txt 文件"
        exit 1
    fi
    
    success "Python 依赖安装完成"
}

# 编译 Live2D
build_live2d() {
    info "编译 Live2D..."
    
    LIVE2D_DIR="$PROJECT_ROOT/src/frontend/live2d"
    
    if [ ! -d "$LIVE2D_DIR" ]; then
        warn "Live2D 目录不存在，跳过编译"
        return 1
    fi
    
    if ! command_exists mvn; then
        warn "未找到 Maven，跳过 Live2D 编译"
        return 1
    fi
    
    cd "$LIVE2D_DIR"
    mvn clean package -DskipTests
    
    if [ $? -eq 0 ]; then
        success "Live2D 编译完成"
        cd "$PROJECT_ROOT"
        return 0
    else
        error "Live2D 编译失败"
        cd "$PROJECT_ROOT"
        return 1
    fi
}

# 配置环境变量
configure_env() {
    info "配置环境变量..."
    
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        if [ -f "$PROJECT_ROOT/.env.example" ]; then
            cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
            warn "已创建 .env 文件，请编辑并填写必要的配置"
            warn "必需配置: OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL"
        else
            error "未找到 .env.example 文件"
            exit 1
        fi
    else
        info ".env 文件已存在"
    fi
    
    success "环境变量配置完成"
}

# 下载模型（可选）
download_models() {
    info "检查模型文件..."
    
    # 检查 TTS 模型
    TTS_MODEL_DIR="$MODELS_DIR/TTS/CosyVoice2-0.5B"
    if [ ! -d "$TTS_MODEL_DIR" ]; then
        warn "未找到 TTS 模型: $TTS_MODEL_DIR"
        warn "首次运行时将自动下载，或手动下载后放置到该目录"
    else
        info "TTS 模型已存在"
    fi
    
    # 检查 ASR 模型
    ASR_MODEL_DIR="$MODELS_DIR/ASR/paraformer-zh-streaming"
    if [ ! -d "$ASR_MODEL_DIR" ]; then
        warn "未找到 ASR 模型: $ASR_MODEL_DIR"
        warn "首次运行时将自动下载，或手动下载后放置到该目录"
    else
        info "ASR 模型已存在"
    fi
}

# 初始化数据库
init_database() {
    info "初始化数据库..."
    
    # 检查 MongoDB 是否运行
    if ! pgrep -x mongod > /dev/null; then
        warn "MongoDB 未运行，跳过数据库初始化"
        warn "请先启动 MongoDB，然后运行: python scripts/setup_database.py --seed"
        return 1
    fi
    
    activate_venv
    
    if [ -f "$PROJECT_ROOT/scripts/setup_database.py" ]; then
        python "$PROJECT_ROOT/scripts/setup_database.py" --seed
        success "数据库初始化完成"
    else
        warn "未找到数据库初始化脚本"
    fi
}

# 启动 MongoDB
start_mongodb() {
    info "启动 MongoDB..."
    
    # 检查是否已经运行
    if pgrep -x mongod > /dev/null; then
        info "MongoDB 已在运行"
        return 0
    fi
    
    # 检查是否安装
    if ! command_exists mongod; then
        warn "未找到 MongoDB，请手动启动 MongoDB"
        return 1
    fi
    
    # 创建数据目录
    MONGO_DATA_DIR="$DATA_DIR/mongodb"
    mkdir -p "$MONGO_DATA_DIR"
    
    # 启动 MongoDB
    mongod --dbpath "$MONGO_DATA_DIR" --logpath "$LOG_DIR/mongodb.log" --fork
    
    if [ $? -eq 0 ]; then
        success "MongoDB 启动成功"
        # 保存 PID
        pgrep -x mongod > "$MONGODB_PID"
        return 0
    else
        error "MongoDB 启动失败，请查看日志: $LOG_DIR/mongodb.log"
        return 1
    fi
}

# 停止 MongoDB
stop_mongodb() {
    info "停止 MongoDB..."
    
    if [ -f "$MONGODB_PID" ]; then
        PID=$(cat "$MONGODB_PID")
        if ps -p $PID > /dev/null 2>&1; then
            kill $PID
            sleep 2
            
            # 强制杀死
            if ps -p $PID > /dev/null 2>&1; then
                kill -9 $PID
            fi
            
            rm -f "$MONGODB_PID"
            success "MongoDB 已停止"
        else
            warn "MongoDB 进程不存在 (PID: $PID)"
            rm -f "$MONGODB_PID"
        fi
    else
        # 尝试查找并停止
        if pgrep -x mongod > /dev/null; then
            pkill -x mongod
            success "MongoDB 已停止"
        else
            info "MongoDB 未运行"
        fi
    fi
}

# 启动主程序
start_main() {
    info "启动主程序..."
    
    # 检查是否已经运行
    if [ -f "$MAIN_PID" ]; then
        PID=$(cat "$MAIN_PID")
        if ps -p $PID > /dev/null 2>&1; then
            warn "主程序已在运行 (PID: $PID)"
            return 0
        else
            rm -f "$MAIN_PID"
        fi
    fi
    
    activate_venv
    
    # 启动主程序
    cd "$PROJECT_ROOT"
    nohup python main.py > "$LOG_DIR/main.log" 2>&1 &
    MAIN_PID_VALUE=$!
    echo $MAIN_PID_VALUE > "$MAIN_PID"
    
    sleep 2
    
    if ps -p $MAIN_PID_VALUE > /dev/null 2>&1; then
        success "主程序启动成功 (PID: $MAIN_PID_VALUE)"
        info "日志文件: $LOG_DIR/main.log"
    else
        error "主程序启动失败，请查看日志: $LOG_DIR/main.log"
        rm -f "$MAIN_PID"
        return 1
    fi
}

# 停止主程序
stop_main() {
    info "停止主程序..."
    
    if [ -f "$MAIN_PID" ]; then
        PID=$(cat "$MAIN_PID")
        if ps -p $PID > /dev/null 2>&1; then
            kill $PID
            sleep 2
            
            # 强制杀死
            if ps -p $PID > /dev/null 2>&1; then
                kill -9 $PID
            fi
            
            rm -f "$MAIN_PID"
            success "主程序已停止"
        else
            warn "主程序进程不存在 (PID: $PID)"
            rm -f "$MAIN_PID"
        fi
    else
        info "主程序未运行"
    fi
}

# 安装
install() {
    print_header
    info "开始安装 玲 (Liying) 智能虚拟助手系统..."
    echo ""
    
    # 检查依赖
    check_python
    check_java
    check_maven
    check_mongodb
    
    echo ""
    
    # 创建目录
    create_directories
    
    # 创建虚拟环境
    create_venv
    
    # 安装依赖
    install_python_dependencies
    
    # 编译 Live2D
    build_live2d
    
    # 配置环境变量
    configure_env
    
    # 下载模型
    download_models
    
    echo ""
    success "========================================="
    success "安装完成！"
    success "========================================="
    echo ""
    info "下一步:"
    info "1. 编辑 .env 文件，填写必要的配置（API Key 等）"
    info "2. 启动 MongoDB: bash deploy.sh start-mongodb"
    info "3. 初始化数据库: bash deploy.sh init-db"
    info "4. 启动系统: bash deploy.sh start"
    echo ""
}

# 启动所有服务
start() {
    print_header
    info "启动所有服务..."
    echo ""
    
    # 启动 MongoDB
    start_mongodb
    
    # 等待 MongoDB 启动
    sleep 2
    
    # 启动主程序
    start_main
    
    echo ""
    success "所有服务已启动"
    info "查看日志: bash deploy.sh logs"
    info "查看状态: bash deploy.sh status"
}

# 停止所有服务
stop() {
    print_header
    info "停止所有服务..."
    echo ""
    
    # 停止主程序
    stop_main
    
    # 停止 MongoDB
    stop_mongodb
    
    echo ""
    success "所有服务已停止"
}

# 重启所有服务
restart() {
    stop
    sleep 2
    start
}

# 查看状态
status() {
    print_header
    info "检查服务状态..."
    echo ""
    
    # MongoDB 状态
    if pgrep -x mongod > /dev/null; then
        success "MongoDB: 运行中"
    else
        warn "MongoDB: 未运行"
    fi
    
    # 主程序状态
    if [ -f "$MAIN_PID" ]; then
        PID=$(cat "$MAIN_PID")
        if ps -p $PID > /dev/null 2>&1; then
            success "主程序: 运行中 (PID: $PID)"
        else
            warn "主程序: 未运行（PID 文件存在但进程不存在）"
        fi
    else
        warn "主程序: 未运行"
    fi
    
    echo ""
}

# 查看日志
logs() {
    if [ -f "$LOG_DIR/main.log" ]; then
        tail -f "$LOG_DIR/main.log"
    else
        warn "日志文件不存在: $LOG_DIR/main.log"
    fi
}

# 清理
clean() {
    print_header
    warn "清理所有数据和缓存..."
    echo ""
    
    read -p "确定要清理吗？这将删除虚拟环境、日志、PID 文件等 (y/N): " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "取消清理"
        return
    fi
    
    # 停止所有服务
    stop
    
    # 删除虚拟环境
    if [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
        info "已删除虚拟环境"
    fi
    
    # 删除日志
    if [ -d "$LOG_DIR" ]; then
        rm -rf "$LOG_DIR"
        info "已删除日志"
    fi
    
    # 删除 PID 文件
    if [ -d "$PID_DIR" ]; then
        rm -rf "$PID_DIR"
        info "已删除 PID 文件"
    fi
    
    # 删除 __pycache__
    find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    info "已删除 Python 缓存"
    
    success "清理完成"
}

# 显示帮助
show_help() {
    print_header
    echo "用法: bash deploy.sh [命令]"
    echo ""
    echo "命令:"
    echo "  install        - 安装依赖和配置环境"
    echo "  start          - 启动所有服务"
    echo "  stop           - 停止所有服务"
    echo "  restart        - 重启所有服务"
    echo "  status         - 查看服务状态"
    echo "  logs           - 查看日志（实时）"
    echo "  start-mongodb  - 仅启动 MongoDB"
    echo "  stop-mongodb   - 仅停止 MongoDB"
    echo "  init-db        - 初始化数据库"
    echo "  clean          - 清理所有数据和缓存"
    echo "  help           - 显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  bash deploy.sh install      # 首次安装"
    echo "  bash deploy.sh start        # 启动系统"
    echo "  bash deploy.sh status       # 查看状态"
    echo "  bash deploy.sh logs         # 查看日志"
    echo ""
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
        start-mongodb)
            start_mongodb
            ;;
        stop-mongodb)
            stop_mongodb
            ;;
        init-db)
            init_database
            ;;
        clean)
            clean
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            show_help
            exit 1
            ;;
    esac
}

main "$@"
