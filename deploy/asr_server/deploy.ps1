# ASR 服务器一键部署脚本 (Windows PowerShell)
# 用法: .\deploy.ps1 [install|start|stop|restart|status]

param(
    [Parameter(Position=0)]
    [ValidateSet('install', 'start', 'stop', 'restart', 'status', 'logs')]
    [string]$Command = 'help'
)

# 配置
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DeployDir = Join-Path $ProjectRoot "deploy\asr_server"
$VenvDir = Join-Path $DeployDir "venv"
$LogDir = Join-Path $DeployDir "logs"
$PidFile = Join-Path $DeployDir "asr_server.pid"
$LogFile = Join-Path $LogDir "asr_server.log"
$Port = 5002
$Host = "0.0.0.0"
$Workers = 4

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
    
    return $pythonCmd
}

# 创建虚拟环境
function Create-Venv {
    param([string]$PythonCmd)
    
    Write-Info "创建虚拟环境..."
    
    if (Test-Path $VenvDir) {
        Write-Warn "虚拟环境已存在，跳过创建"
    } else {
        & $PythonCmd -m venv $VenvDir
        Write-Info "虚拟环境创建完成: $VenvDir"
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

# 安装依赖
function Install-Dependencies {
    Write-Info "安装依赖..."
    
    Activate-Venv
    
    # 升级 pip
    python -m pip install --upgrade pip
    
    # 安装依赖
    $requirementsFile = Join-Path $DeployDir "requirements.txt"
    
    if (Test-Path $requirementsFile) {
        pip install -r $requirementsFile
    } else {
        # 基础依赖
        pip install flask gunicorn requests numpy
        
        # FunASR 和 PyTorch
        pip install funasr torch torchaudio
        
        # 其他依赖
        pip install sounddevice librosa
    }
    
    Write-Info "依赖安装完成"
}

# 检查模型
function Check-Models {
    Write-Info "检查模型..."
    
    $modelDir = Join-Path $ProjectRoot "models\ASR"
    
    $paraformerPath = Join-Path $modelDir "paraformer-zh-streaming"
    if (-not (Test-Path $paraformerPath)) {
        Write-Warn "未找到 Paraformer 模型，首次运行时将自动下载"
    } else {
        Write-Info "Paraformer 模型已存在"
    }
    
    $vadPath = Join-Path $modelDir "fsmn-vad"
    if (-not (Test-Path $vadPath)) {
        Write-Warn "未找到 VAD 模型，首次运行时将自动下载"
    } else {
        Write-Info "VAD 模型已存在"
    }
}

# 创建日志目录
function Create-LogDir {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
        Write-Info "创建日志目录: $LogDir"
    }
}

# 安装
function Install-Server {
    Write-Info "开始安装 ASR 服务器..."
    Write-Host "================================"
    
    $pythonCmd = Check-Python
    Create-Venv -PythonCmd $pythonCmd
    Install-Dependencies
    Check-Models
    Create-LogDir
    
    Write-Host "================================"
    Write-Info "安装完成！"
    Write-Info "使用 '.\deploy.ps1 start' 启动服务器"
}

# 启动服务器
function Start-Server {
    Write-Info "启动 ASR 服务器..."
    
    # 检查是否已经在运行
    if (Test-Path $PidFile) {
        $pid = Get-Content $PidFile
        $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
        
        if ($process) {
            Write-Warn "服务器已在运行 (PID: $pid)"
            return
        } else {
            Write-Warn "PID 文件存在但进程不存在，清理 PID 文件"
            Remove-Item $PidFile -Force
        }
    }
    
    # 检查虚拟环境
    if (-not (Test-Path $VenvDir)) {
        Write-Error-Custom "虚拟环境不存在，请先运行: .\deploy.ps1 install"
        exit 1
    }
    
    Activate-Venv
    
    # 启动服务器
    Push-Location $DeployDir
    
    Write-Info "启动服务器..."
    Write-Info "监听地址: ${Host}:${Port}"
    Write-Info "日志文件: $LogFile"
    
    # 使用 Start-Process 在后台启动
    $pythonExe = Join-Path $VenvDir "Scripts\python.exe"
    $serverScript = Join-Path $DeployDir "server.py"
    
    $process = Start-Process -FilePath $pythonExe `
        -ArgumentList $serverScript, "--host", $Host, "--port", $Port `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $LogFile `
        -RedirectStandardError (Join-Path $LogDir "error.log")
    
    # 保存 PID
    $process.Id | Out-File -FilePath $PidFile -Encoding ASCII
    
    Start-Sleep -Seconds 2
    
    if (Test-Path $PidFile) {
        $pid = Get-Content $PidFile
        Write-Info "服务器已启动 (PID: $pid)"
        Write-Info "访问地址: http://${Host}:${Port}"
        Write-Info "健康检查: curl http://localhost:${Port}/health"
    } else {
        Write-Error-Custom "服务器启动失败，请查看日志: $LogFile"
        exit 1
    }
    
    Pop-Location
}

# 停止服务器
function Stop-Server {
    Write-Info "停止 ASR 服务器..."
    
    if (-not (Test-Path $PidFile)) {
        Write-Warn "PID 文件不存在，服务器可能未运行"
        return
    }
    
    $pid = Get-Content $PidFile
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    
    if ($process) {
        Stop-Process -Id $pid -Force
        Start-Sleep -Seconds 2
        
        Remove-Item $PidFile -Force
        Write-Info "服务器已停止"
    } else {
        Write-Warn "进程不存在 (PID: $pid)"
        Remove-Item $PidFile -Force
    }
}

# 重启服务器
function Restart-Server {
    Write-Info "重启 ASR 服务器..."
    Stop-Server
    Start-Sleep -Seconds 2
    Start-Server
}

# 查看状态
function Get-ServerStatus {
    Write-Info "检查 ASR 服务器状态..."
    
    if (-not (Test-Path $PidFile)) {
        Write-Warn "服务器未运行（PID 文件不存在）"
        return
    }
    
    $pid = Get-Content $PidFile
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    
    if ($process) {
        Write-Info "服务器正在运行 (PID: $pid)"
        
        # 检查端口
        $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($connection) {
            Write-Info "端口 $Port 正在监听"
        } else {
            Write-Warn "端口 $Port 未监听"
        }
        
        # 健康检查
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:${Port}/health" -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                Write-Info "健康检查通过 ✓"
            } else {
                Write-Warn "健康检查失败 ✗"
            }
        } catch {
            Write-Warn "健康检查失败: $_"
        }
    } else {
        Write-Warn "服务器未运行（进程不存在）"
        Remove-Item $PidFile -Force
    }
}

# 查看日志
function Show-Logs {
    if (Test-Path $LogFile) {
        Get-Content $LogFile -Wait -Tail 50
    } elseif (Test-Path (Join-Path $LogDir "error.log")) {
        Get-Content (Join-Path $LogDir "error.log") -Wait -Tail 50
    } else {
        Write-Warn "日志文件不存在"
    }
}

# 显示帮助
function Show-Help {
    Write-Host "ASR 服务器部署脚本 (Windows)"
    Write-Host ""
    Write-Host "用法: .\deploy.ps1 [命令]"
    Write-Host ""
    Write-Host "命令:"
    Write-Host "  install   - 安装依赖和配置环境"
    Write-Host "  start     - 启动服务器"
    Write-Host "  stop      - 停止服务器"
    Write-Host "  restart   - 重启服务器"
    Write-Host "  status    - 查看服务器状态"
    Write-Host "  logs      - 查看日志（实时）"
    Write-Host ""
    Write-Host "示例:"
    Write-Host "  .\deploy.ps1 install   # 首次安装"
    Write-Host "  .\deploy.ps1 start     # 启动服务器"
    Write-Host "  .\deploy.ps1 status    # 查看状态"
}

# 主函数
switch ($Command) {
    'install' { Install-Server }
    'start' { Start-Server }
    'stop' { Stop-Server }
    'restart' { Restart-Server }
    'status' { Get-ServerStatus }
    'logs' { Show-Logs }
    default { Show-Help }
}
