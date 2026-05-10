@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM ASR 服务器一键部署脚本（完整版 Windows）
REM 支持自动检测环境、下载模型、配置服务
REM ============================================================

set PORT=5002
set USE_GPU=false
set MODEL_DIR=models\ASR
set SKIP_MODEL_DOWNLOAD=false

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
if "%~1"=="--skip-models" (
    set SKIP_MODEL_DOWNLOAD=true
    shift
    goto :parse_args
)
if "%~1"=="--help" (
    echo 用法: one_click_deploy.bat [选项]
    echo.
    echo 选项:
    echo   --gpu           安装 GPU 版本的 PyTorch
    echo   --port PORT     指定服务端口 (默认: 5002)
    echo   --skip-models   跳过模型下载
    echo   --help          显示此帮助信息
    exit /b 0
)
echo 未知参数: %~1
exit /b 1

:start_deploy
echo ============================================
echo   ASR 服务器一键部署
echo ============================================
echo.

REM 1. 检测 Python
echo [1/8] 检测 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python
    echo 请安装 Python 3.8+ 并添加到 PATH
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [SUCCESS] %PYTHON_VERSION%

REM 2. 检测 GPU
echo [2/8] 检测 GPU...
if "%USE_GPU%"=="true" (
    nvidia-smi >nul 2>&1
    if errorlevel 1 (
        echo [WARN] 未找到 nvidia-smi，将使用 CPU
        set USE_GPU=false
    ) else (
        for /f "tokens=*" %%i in ('nvidia-smi --query-gpu^=name --format^=csv^,noheader 2^>nul') do (
            echo [SUCCESS] GPU: %%i
            goto :gpu_found
        )
        :gpu_found
    )
) else (
    echo [INFO] 使用 CPU 模式
)

REM 3. 创建目录结构
echo [3/8] 创建目录结构...
if not exist "%MODEL_DIR%" mkdir "%MODEL_DIR%"
if not exist "logs" mkdir "logs"
echo [SUCCESS] 目录创建完成

REM 4. 安装 Python 依赖
echo [4/8] 安装 Python 依赖...
python -m pip install --upgrade pip

if "%USE_GPU%"=="true" (
    echo [INFO] 安装 GPU 版本 PyTorch...
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
) else (
    echo [INFO] 安装 CPU 版本 PyTorch...
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
)

echo [INFO] 安装其他依赖...
pip install -r requirements.txt
echo [SUCCESS] 依赖安装完成

REM 5. 下载模型
if "%SKIP_MODEL_DOWNLOAD%"=="false" (
    echo [5/8] 下载 ASR 模型...

    python -c "
import os
from pathlib import Path

model_dir = Path('models/ASR')
model_dir.mkdir(parents=True, exist_ok=True)

def download_model(model_id, local_dir):
    local_path = model_dir / local_dir
    if local_path.exists() and any(local_path.iterdir()):
        print(f'✓ {local_dir} 已存在，跳过下载')
        return True

    print(f'正在下载 {model_id}...')
    try:
        from modelscope.hub.snapshot_download import snapshot_download
        snapshot_download(model_id, local_dir=str(local_path))
        print(f'✓ {local_dir} 下载完成')
        return True
    except Exception as e:
        print(f'ModelScope 下载失败: {e}')

    try:
        from huggingface_hub import snapshot_download as hf_download
        hf_download(
            repo_id=model_id.replace('iic/', 'funasr/'),
            local_dir=str(local_path)
        )
        print(f'✓ {local_dir} 下载完成 (HuggingFace)')
        return True
    except Exception as e:
        print(f'HuggingFace 下载失败: {e}')

    print(f'⚠ {local_dir} 下载失败，将在首次运行时自动下载')
    return False

download_model('iic/speech_paraformer-zh-streaming', 'paraformer-zh-streaming')
download_model('iic/speech_fsmn_vad_zh-cn-16k-common-pytorch', 'fsmn-vad')
download_model('iic/punc_ct-transformer_zh-cn-common-vad_realtime-vocab272727', 'punc_ct-transformer')
"

    echo [SUCCESS] 模型下载完成
) else (
    echo [5/8] 跳过模型下载...
)

REM 6. 验证模型
echo [6/8] 验证模型文件...
if exist "%MODEL_DIR%\paraformer-zh-streaming\model.pt" (
    echo [SUCCESS] Paraformer 模型已就绪
) else (
    echo [WARN] Paraformer 模型未找到，将在首次运行时自动下载
)

if exist "%MODEL_DIR%\fsmn-vad" (
    echo [SUCCESS] VAD 模型已就绪
) else (
    echo [WARN] VAD 模型未找到，将在首次运行时自动下载
)

REM 7. 创建启动脚本
echo [7/8] 创建启动脚本...

(
echo @echo off
echo REM ASR 服务器启动脚本
echo.
echo echo ============================================
echo echo   ASR 服务器启动
echo echo ============================================
echo echo.
echo echo 端口: %PORT%
echo echo GPU: %USE_GPU%
echo echo 模型目录: %MODEL_DIR%
echo echo.
echo.
echo set FUNASR_CACHE_DIR=%MODEL_DIR%
echo.
if "%USE_GPU%"=="true" (
    echo python server.py --host 0.0.0.0 --port %PORT% --device cuda:0
) else (
    echo python server.py --host 0.0.0.0 --port %PORT% --device cpu
)
echo pause
) > start.bat

REM 创建停止脚本
(
echo @echo off
echo REM ASR 服务器停止脚本
echo.
echo echo 正在停止 ASR 服务器...
echo.
echo taskkill /F /IM python.exe /FI "WINDOWTITLE eq *server.py*" ^>nul 2^>^&1
echo if errorlevel 1 echo 未找到运行中的 ASR 服务器
echo pause
) > stop.bat

REM 创建健康检查脚本
(
echo @echo off
echo REM 健康检查脚本
echo.
echo echo 检查 ASR 服务器状态...
echo.
echo curl -s http://localhost:%PORT%/health ^>nul 2^>^&1
echo if errorlevel 1 echo [ERROR] 服务器未响应
echo.
echo curl -s http://localhost:%PORT%/health
echo echo.
echo pause
) > health_check.bat

echo [SUCCESS] 启动脚本创建完成

REM 8. 创建测试脚本
echo [8/8] 创建测试脚本...

(
echo @echo off
echo REM 测试语音识别
echo.
echo if "%%~1"=="" echo 用法: test_recognize.bat ^<音频文件^>
echo if "%%~1"=="" echo 示例: test_recognize.bat test.wav
echo if "%%~1"=="" pause
echo if "%%~1"=="" exit /b 1
echo.
echo if not exist "%%~1" echo 错误: 文件不存在 - %%~1
echo if not exist "%%~1" pause
echo if not exist "%%~1" exit /b 1
echo.
echo echo 正在识别: %%~1
echo.
echo for /f "tokens=*" %%%%i in ('certutil -encode "%%~1" temp.b64 ^| findstr /v "Certificate"') do set AUDIO_B64=%%%%i
echo.
echo curl -X POST http://localhost:%PORT%/asr/recognize -H "Content-Type: application/json" -d "{\"audio\": \"!AUDIO_B64!\"}"
echo.
echo del temp.b64 ^>nul 2^>^&1
echo pause
) > test_recognize.bat

echo [SUCCESS] 测试脚本创建完成

echo.
echo ============================================
echo [SUCCESS] 部署完成！
echo ============================================
echo.
echo 📁 目录结构:
echo   ├── server.py           # 服务器主程序
echo   ├── requirements.txt    # Python 依赖
echo   ├── models\ASR\         # 模型目录
echo   ├── start.bat           # 启动脚本
echo   ├── stop.bat            # 停止脚本
echo   ├── health_check.bat    # 健康检查
echo   └── test_recognize.bat  # 测试脚本
echo.
echo 🚀 快速启动:
echo   start.bat
echo.
echo 🧪 验证服务:
echo   health_check.bat
echo.
echo 🎤 测试识别:
echo   test_recognize.bat test.wav
echo.
echo 📊 查看日志:
echo   type logs\asr_server.log
echo.
echo 📚 更多信息请查看 DEPLOYMENT_GUIDE.md
echo.

pause
