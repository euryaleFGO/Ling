# 玲 (Liying) - 智能虚拟助手系统
# 一键部署脚本 (Windows PowerShell)
# 用法: .\deploy.ps1 [install|start|stop|restart|status|logs|clean]

param(
    [Parameter(Position=0)]
    [ValidateSet('install', 'start', 'stop', 'restart', 'status', 'logs', 'start-mongodb', 'stop-mongodb', 'init-db', 'clean', 'help')]
    [string]$Command = 'help'
)

# 配置
$ProjectRoot = $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot "venv"
$LogDir = Join-Path $ProjectRoot "logs"
$PidDir = Join-Path $ProjectRoot ".pids"
$ModelsDir = Join-Path $ProjectRoot "models"
$DataDir = Join-Path $ProjectRoot "data"

# PID 文件
$MongoDBPid = Join-Path $PidDir "mongodb.pid"
$MainPid = Join-Path $PidDir "main.pid"

# 颜色输出
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

# 打印标题
function Print-Header {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Blue
    Write-Host "  玲 (Liying) - 智能虚拟助手系统" -ForegroundColor Blue
    Write-Host "========================================" -ForegroundColor Blue
    Write-Host ""
}

# 检查 Python 版本
function Check-Python {
    Write-Info "检查 Python 版本..."
    
    $pythonCmd = $null
    
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $pythonCmd = "python"
    } elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
        $pythonCmd = "python3"
    } else {
        Write-Error-Custom "未找到 Python，请先安装 Python 3.8+"
        exit 1
    }
    
    $version = & $pythonCmd --version 2>&1
    Write-Info "Python 版本: $version"
    
    # 检查版本
    $versionMatch = $version -match "Python (\d+)\.(\d+)"
    if ($versionMatch) {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
            Write-Error-Custom "Python 版本过低，需要 3.8+，当前版本: $version"
            exit 1
        }
    }
    
    Write-Success "Python 版本检查通过"
    return $pythonCmd
}

# 检查 Java 版本
function Check-Java {
    Write-Info "检查 Java 版本..."
    
    if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
        Write-Warn "未找到 Java，Live2D 功能将无法使用"
        Write-Warn "请安装 Java 17+ 以启用 Live2D 功能"
        return $false
    }
    
    $version = java -version 2>&1 | Select-String -Pattern "version" | Select-Object -First 1
    Write-Info "Java 版本: $version"
    
    # 检查版本是否 >= 17
    if ($version -match '"(\d+)') {
        $major = [int]$Matches[1]
        if ($major -lt 17) {
            Write-Warn "Java 版本过低，需要 17+，当前版本: $major"
            Write-Warn "Live2D 功能可能无法正常工作"
            return $false
        }
    }
    
    Write-Success "Java 版本检查通过"
    return $true
}

# 检查 Maven
function Check-Maven {
    Write-Info "检查 Maven..."
    
    if (-not (Get-Command mvn -ErrorAction SilentlyContinue)) {
        Write-Warn "未找到 Maven，将使用预编译的 JAR 文件"
        return $false
    }
    
    $version = mvn -version 2>&1 | Select-String -Pattern "Apache Maven" | Select-Object -First 1
    Write-Info "Maven 版本: $version"
    Write-Success "Maven 检查通过"
    return $true
}

# 检查 MongoDB
function Check-MongoDB {
    Write-Info "检查 MongoDB..."
    
    if (-not (Get-Command mongod -ErrorAction SilentlyContinue)) {
        Write-Warn "未找到 MongoDB，请手动安装 MongoDB"
        Write-Warn "下载地址: https://www.mongodb.com/try/download/community"
        Write-Warn "或使用 Docker: docker run -d -p 27017:27017 --name mongodb mongo:latest"
        return $false
    }
    
    $version = mongod --version 2>&1 | Select-String -Pattern "db version" | Select-Object -First 1
    Write-Info "MongoDB 版本: $version"
    Write-Success "MongoDB 检查通过"
    return $true
}

# 创建必要的目录
function Create-Directories {
    Write-Info "创建必要的目录..."
    
    $dirs = @($LogDir, $PidDir, $ModelsDir, $DataDir,
              (Join-Path $DataDir "chroma_data"),
              (Join-Path $DataDir "dreams"),
              (Join-Path $DataDir "screenshots"),
              (Join-Path $DataDir "camera"),
              (Join-Path $DataDir "txt"))
    
    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir | Out-Null
        }
    }
    
    Write-Success "目录创建完成"
}

# 创建虚拟环境
function Create-Venv {
    param([string]$PythonCmd)
    
    Write-Info "创建 Python 虚拟环境..."
    
    if (Test-Path $VenvDir) {
        Write-Warn "虚拟环境已存在，跳过创建"
    } else {
        & $PythonCmd -m venv $VenvDir
        Write-Success "虚拟环境创建完成: $VenvDir"
    }
}

# 激活虚拟环境
function Activate-Venv {
    $activateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
    
    if (Test-Path $activateScript) {
        & $activateScript
    } else {
        Write-Error-Custom "虚拟环境激活脚本不存在: $activateScript"
        exit 1
    }
}

# 安装 Python 依赖
function Install-PythonDependencies {
    Write-Info "安装 Python 依赖..."
    
    Activate-Venv
    
    # 升级 pip
    python -m pip install --upgrade pip
    
    # 安装 PyTorch (CUDA 12.1)
    Write-Info "安装 PyTorch (CUDA 12.1)..."
    pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121
    
    # 安装其他依赖
    $requirementsFile = Join-Path $ProjectRoot "requirements.txt"
    
    if (Test-Path $requirementsFile) {
        Write-Info "安装项目依赖..."
        pip install -r $requirementsFile
    } else {
        Write-Error-Custom "未找到 requirements.txt 文件"
        exit 1
    }
    
    Write-Success "Python 依赖安装完成"
}

# 编译 Live2D
function Build-Live2D {
    Write-Info "编译 Live2D..."
    
    $live2dDir = Join-Path $ProjectRoot "src\frontend\live2d"
    
    if (-not (Test-Path $live2dDir)) {
        Write-Warn "Live2D 目录不存在，跳过编译"
        return $false
    }
    
    if (-not (Get-Command mvn -ErrorAction SilentlyContinue)) {
        Write-Warn "未找到 Maven，跳过 Live2D 编译"
        return $false
    }
    
    Push-Location $live2dDir
    mvn clean package -DskipTests
    $result = $LASTEXITCODE
    Pop-Location
    
    if ($result -eq 0) {
        Write-Success "Live2D 编译完成"
        return $true
    } else {
        Write-Error-Custom "Live2D 编译失败"
        return $false
    }
}

# 配置环境变量
function Configure-Env {
    Write-Info "配置环境变量..."
    
    $envFile = Join-Path $ProjectRoot ".env"
    $envExampleFile = Join-Path $ProjectRoot ".env.example"
    
    if (-not (Test-Path $envFile)) {
        if (Test-Path $envExampleFile) {
            Copy-Item $envExampleFile $envFile
            Write-Warn "已创建 .env 文件，请编辑并填写必要的配置"
            Write-Warn "必需配置: OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL"
        } else {
            Write-Error-Custom "未找到 .env.example 文件"
            exit 1
        }
    } else {
        Write-Info ".env 文件已存在"
    }
    
    Write-Success "环境变量配置完成"
}

# 下载模型（可选）
function Download-Models {
    Write-Info "检查模型文件..."
    
    # 检查 TTS 模型
    $ttsModelDir = Join-Path $ModelsDir "TTS\CosyVoice2-0.5B"
    if (-not (Test-Path $ttsModelDir)) {
        Write-Warn "未找到 TTS 模型: $ttsModelDir"
        Write-Warn "首次运行时将自动下载，或手动下载后放置到该目录"
    } else {
        Write-Info "TTS 模型已存在"
    }
    
    # 检查 ASR 模型
    $asrModelDir = Join-Path $ModelsDir "ASR\paraformer-zh-streaming"
    if (-not (Test-Path $asrModelDir)) {
        Write-Warn "未找到 ASR 模型: $asrModelDir"
        Write-Warn "首次运行时将自动下载，或手动下载后放置到该目录"
    } else {
        Write-Info "ASR 模型已存在"
    }
}

# 初始化数据库
function Init-Database {
    Write-Info "初始化数据库..."
    
    # 检查 MongoDB 是否运行
    $mongoProcess = Get-Process -Name mongod -ErrorAction SilentlyContinue
    if (-not $mongoProcess) {
        Write-Warn "MongoDB 未运行，跳过数据库初始化"
        Write-Warn "请先启动 MongoDB，然后运行: python scripts\setup_database.py --seed"
        return $false
    }
    
    Activate-Venv
    
    $setupScript = Join-Path $ProjectRoot "scripts\setup_database.py"
    if (Test-Path $setupScript) {
        python $setupScript --seed
        Write-Success "数据库初始化完成"
        return $true
    } else {
        Write-Warn "未找到数据库初始化脚本"
        return $false
    }
}

# 启动 MongoDB
function Start-MongoDB {
    Write-Info "启动 MongoDB..."
    
    # 检查是否已经运行
    $mongoProcess = Get-Process -Name mongod -ErrorAction SilentlyContinue
    if ($mongoProcess) {
        Write-Info "MongoDB 已在运行"
        return $true
    }
    
    # 检查是否安装
    if (-not (Get-Command mongod -ErrorAction SilentlyContinue)) {
        Write-Warn "未找到 MongoDB，请手动启动 MongoDB"
        return $false
    }
    
    # 创建数据目录
    $mongoDataDir = Join-Path $DataDir "mongodb"
    if (-not (Test-Path $mongoDataDir)) {
        New-Item -ItemType Directory -Path $mongoDataDir | Out-Null
    }
    
    # 启动 MongoDB
    $mongoLogFile = Join-Path $LogDir "mongodb.log"
    $process = Start-Process -FilePath "mongod" `
        -ArgumentList "--dbpath", $mongoDataDir, "--logpath", $mongoLogFile `
        -WindowStyle Hidden `
        -PassThru
    
    if ($process) {
        $process.Id | Out-File -FilePath $MongoDBPid -Encoding ASCII
        Write-Success "MongoDB 启动成功 (PID: $($process.Id))"
        return $true
    } else {
        Write-Error-Custom "MongoDB 启动失败，请查看日志: $mongoLogFile"
        return $false
    }
}

# 停止 MongoDB
function Stop-MongoDB {
    Write-Info "停止 MongoDB..."
    
    if (Test-Path $MongoDBPid) {
        $pid = Get-Content $MongoDBPid
        $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
        
        if ($process) {
            Stop-Process -Id $pid -Force
            Start-Sleep -Seconds 2
            Remove-Item $MongoDBPid -Force
            Write-Success "MongoDB 已停止"
        } else {
            Write-Warn "MongoDB 进程不存在 (PID: $pid)"
            Remove-Item $MongoDBPid -Force
        }
    } else {
        # 尝试查找并停止
        $mongoProcess = Get-Process -Name mongod -ErrorAction SilentlyContinue
        if ($mongoProcess) {
            Stop-Process -Name mongod -Force
            Write-Success "MongoDB 已停止"
        } else {
            Write-Info "MongoDB 未运行"
        }
    }
}

# 启动主程序
function Start-Main {
    Write-Info "启动主程序..."
    
    # 检查是否已经运行
    if (Test-Path $MainPid) {
        $pid = Get-Content $MainPid
        $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
        
        if ($process) {
            Write-Warn "主程序已在运行 (PID: $pid)"
            return $true
        } else {
            Remove-Item $MainPid -Force
        }
    }
    
    Activate-Venv
    
    # 启动主程序
    $mainScript = Join-Path $ProjectRoot "main.py"
    $mainLogFile = Join-Path $LogDir "main.log"
    
    $process = Start-Process -FilePath "python" `
        -ArgumentList $mainScript `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $mainLogFile `
        -RedirectStandardError (Join-Path $LogDir "main_error.log")
    
    if ($process) {
        $process.Id | Out-File -FilePath $MainPid -Encoding ASCII
        Start-Sleep -Seconds 2
        
        if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
            Write-Success "主程序启动成功 (PID: $($process.Id))"
            Write-Info "日志文件: $mainLogFile"
            return $true
        } else {
            Write-Error-Custom "主程序启动失败，请查看日志: $mainLogFile"
            Remove-Item $MainPid -Force
            return $false
        }
    } else {
        Write-Error-Custom "主程序启动失败"
        return $false
    }
}

# 停止主程序
function Stop-Main {
    Write-Info "停止主程序..."
    
    if (Test-Path $MainPid) {
        $pid = Get-Content $MainPid
        $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
        
        if ($process) {
            Stop-Process -Id $pid -Force
            Start-Sleep -Seconds 2
            Remove-Item $MainPid -Force
            Write-Success "主程序已停止"
        } else {
            Write-Warn "主程序进程不存在 (PID: $pid)"
            Remove-Item $MainPid -Force
        }
    } else {
        Write-Info "主程序未运行"
    }
}

# 安装
function Install-System {
    Print-Header
    Write-Info "开始安装 玲 (Liying) 智能虚拟助手系统..."
    Write-Host ""
    
    # 检查依赖
    $pythonCmd = Check-Python
    Check-Java | Out-Null
    Check-Maven | Out-Null
    Check-MongoDB | Out-Null
    
    Write-Host ""
    
    # 创建目录
    Create-Directories
    
    # 创建虚拟环境
    Create-Venv -PythonCmd $pythonCmd
    
    # 安装依赖
    Install-PythonDependencies
    
    # 编译 Live2D
    Build-Live2D | Out-Null
    
    # 配置环境变量
    Configure-Env
    
    # 下载模型
    Download-Models
    
    Write-Host ""
    Write-Success "========================================="
    Write-Success "安装完成！"
    Write-Success "========================================="
    Write-Host ""
    Write-Info "下一步:"
    Write-Info "1. 编辑 .env 文件，填写必要的配置（API Key 等）"
    Write-Info "2. 启动 MongoDB: .\deploy.ps1 start-mongodb"
    Write-Info "3. 初始化数据库: .\deploy.ps1 init-db"
    Write-Info "4. 启动系统: .\deploy.ps1 start"
    Write-Host ""
}

# 启动所有服务
function Start-System {
    Print-Header
    Write-Info "启动所有服务..."
    Write-Host ""
    
    # 启动 MongoDB
    Start-MongoDB | Out-Null
    
    # 等待 MongoDB 启动
    Start-Sleep -Seconds 2
    
    # 启动主程序
    Start-Main | Out-Null
    
    Write-Host ""
    Write-Success "所有服务已启动"
    Write-Info "查看日志: .\deploy.ps1 logs"
    Write-Info "查看状态: .\deploy.ps1 status"
}

# 停止所有服务
function Stop-System {
    Print-Header
    Write-Info "停止所有服务..."
    Write-Host ""
    
    # 停止主程序
    Stop-Main
    
    # 停止 MongoDB
    Stop-MongoDB
    
    Write-Host ""
    Write-Success "所有服务已停止"
}

# 重启所有服务
function Restart-System {
    Stop-System
    Start-Sleep -Seconds 2
    Start-System
}

# 查看状态
function Get-SystemStatus {
    Print-Header
    Write-Info "检查服务状态..."
    Write-Host ""
    
    # MongoDB 状态
    $mongoProcess = Get-Process -Name mongod -ErrorAction SilentlyContinue
    if ($mongoProcess) {
        Write-Success "MongoDB: 运行中 (PID: $($mongoProcess.Id))"
    } else {
        Write-Warn "MongoDB: 未运行"
    }
    
    # 主程序状态
    if (Test-Path $MainPid) {
        $pid = Get-Content $MainPid
        $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
        
        if ($process) {
            Write-Success "主程序: 运行中 (PID: $pid)"
        } else {
            Write-Warn "主程序: 未运行（PID 文件存在但进程不存在）"
        }
    } else {
        Write-Warn "主程序: 未运行"
    }
    
    Write-Host ""
}

# 查看日志
function Show-Logs {
    $mainLogFile = Join-Path $LogDir "main.log"
    
    if (Test-Path $mainLogFile) {
        Get-Content $mainLogFile -Wait -Tail 50
    } else {
        Write-Warn "日志文件不存在: $mainLogFile"
    }
}

# 清理
function Clean-System {
    Print-Header
    Write-Warn "清理所有数据和缓存..."
    Write-Host ""
    
    $confirmation = Read-Host "确定要清理吗？这将删除虚拟环境、日志、PID 文件等 (y/N)"
    
    if ($confirmation -ne 'y' -and $confirmation -ne 'Y') {
        Write-Info "取消清理"
        return
    }
    
    # 停止所有服务
    Stop-System
    
    # 删除虚拟环境
    if (Test-Path $VenvDir) {
        Remove-Item $VenvDir -Recurse -Force
        Write-Info "已删除虚拟环境"
    }
    
    # 删除日志
    if (Test-Path $LogDir) {
        Remove-Item $LogDir -Recurse -Force
        Write-Info "已删除日志"
    }
    
    # 删除 PID 文件
    if (Test-Path $PidDir) {
        Remove-Item $PidDir -Recurse -Force
        Write-Info "已删除 PID 文件"
    }
    
    # 删除 __pycache__
    Get-ChildItem -Path $ProjectRoot -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
    Write-Info "已删除 Python 缓存"
    
    Write-Success "清理完成"
}

# 显示帮助
function Show-Help {
    Print-Header
    Write-Host "用法: .\deploy.ps1 [命令]"
    Write-Host ""
    Write-Host "命令:"
    Write-Host "  install        - 安装依赖和配置环境"
    Write-Host "  start          - 启动所有服务"
    Write-Host "  stop           - 停止所有服务"
    Write-Host "  restart        - 重启所有服务"
    Write-Host "  status         - 查看服务状态"
    Write-Host "  logs           - 查看日志（实时）"
    Write-Host "  start-mongodb  - 仅启动 MongoDB"
    Write-Host "  stop-mongodb   - 仅停止 MongoDB"
    Write-Host "  init-db        - 初始化数据库"
    Write-Host "  clean          - 清理所有数据和缓存"
    Write-Host "  help           - 显示此帮助信息"
    Write-Host ""
    Write-Host "示例:"
    Write-Host "  .\deploy.ps1 install      # 首次安装"
    Write-Host "  .\deploy.ps1 start        # 启动系统"
    Write-Host "  .\deploy.ps1 status       # 查看状态"
    Write-Host "  .\deploy.ps1 logs         # 查看日志"
    Write-Host ""
}

# 主函数
switch ($Command) {
    'install' { Install-System }
    'start' { Start-System }
    'stop' { Stop-System }
    'restart' { Restart-System }
    'status' { Get-SystemStatus }
    'logs' { Show-Logs }
    'start-mongodb' { Start-MongoDB }
    'stop-mongodb' { Stop-MongoDB }
    'init-db' { Init-Database }
    'clean' { Clean-System }
    default { Show-Help }
}
