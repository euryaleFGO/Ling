@echo off
REM ============================================================
REM ASR 服务器一键部署脚本 (Windows)
REM 用法: setup.bat [--gpu] [--port 5002]
REM ============================================================

setlocal enabledelayedexpansion

set PORT=5002
set USE_GPU=false
set MODEL_DIR=models\ASR

REM 解析参数
:parse_args
if "%~1"=="" goto :start_deploy
if "%~1"=="--gpu" (
    set USE_GPU=true
    shift
    goto :parse_args
)
if "%~1"=="--port" (
    set PORT=%~2
    shift
    shift
    goto :parse_args
)
if "%~1"=="--help" (
    echo 用法: setup.bat [选项]
    echo.
    echo 选项:
    echo   --gpu       安装 GPU 版本的 PyTorch
    echo   --port PORT 指定服务端口 (默认: 5002)
    echo   --help      显示此帮助信息
    exit /b 0
)
echo 未知参数: %~1
exit /b 1

:start_deploy
echo ============================================
echo   ASR 服务器一键部署
echo ============================================
echo.

REM 1. 检查 Python 版本
echo [1/5] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python
    echo 请安装 Python 3.8+ 并添加到 PATH
    exit /b 1
)

REM 2. 安装 Python 依赖
echo [2/5] 安装 Python 依赖...
python -m pip install --upgrade pip

if "%USE_GPU%"=="true" (
    echo 安装 GPU 版本 PyTorch...
    python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
) else (
    echo 安装 CPU 版本 PyTorch...
    python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
)

python -m pip install -r requirements.txt

REM 3. 下载模型
echo [3/5] 下载 ASR 模型...
if not exist "%MODEL_DIR%" mkdir "%MODEL_DIR%"

python -c "
import os
from pathlib import Path

model_dir = Path('models/ASR')
model_dir.mkdir(parents=True, exist_ok=True)

print('正在下载 Paraformer 流式模型...')
try:
    from modelscope.hub.snapshot_download import snapshot_download as ms_download
    ms_download(
        'iic/speech_paraformer-zh-streaming',
        local_dir=str(model_dir / 'paraformer-zh-streaming')
    )
    print('Paraformer 模型下载完成')
except Exception as e:
    print(f'ModelScope 下载失败: {e}')
    print('尝试使用 FunASR 自动下载...')

print('正在下载 VAD 模型...')
try:
    from modelscope.hub.snapshot_download import snapshot_download as ms_download
    ms_download(
        'iic/speech_fsmn_vad_zh-cn-16k-common-pytorch',
        local_dir=str(model_dir / 'fsmn-vad')
    )
    print('VAD 模型下载完成')
except Exception as e:
    print(f'VAD 模型下载失败: {e}')
    print('VAD 模型将在首次使用时自动下载')
"

REM 4. 验证模型
echo [4/5] 验证模型文件...
if exist "%MODEL_DIR%\paraformer-zh-streaming" (
    echo ✓ Paraformer 模型已就绪
) else (
    echo ⚠ Paraformer 模型未找到，将在首次运行时自动下载
)

if exist "%MODEL_DIR%\fsmn-vad" (
    echo ✓ VAD 模型已就绪
) else (
    echo ⚠ VAD 模型未找到，将在首次运行时自动下载
)

REM 5. 创建启动脚本
echo [5/5] 创建启动脚本...

(
echo @echo off
echo REM ASR 服务器启动脚本
echo.
echo echo 启动 ASR 服务器...
echo echo 端口: %PORT%
echo echo GPU: %USE_GPU%
echo echo.
echo.
if "%USE_GPU%"=="true" (
    echo python server.py --host 0.0.0.0 --port %PORT% --device cuda:0
) else (
    echo python server.py --host 0.0.0.0 --port %PORT% --device cpu
)
) > start.bat

echo.
echo ============================================
echo   部署完成！
echo ============================================
echo.
echo 启动服务:
echo   start.bat
echo.
echo 验证服务:
echo   curl http://localhost:%PORT%/health
echo.

endlocal
