@echo off
echo ============================================================
echo         企业微信应用机器人 - 玲 (Liying)
echo ============================================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python
    pause
    exit /b 1
)

REM 检查依赖
echo 检查依赖...
pip show flask >nul 2>&1
if errorlevel 1 (
    echo 安装 Flask...
    pip install flask
)

pip show requests >nul 2>&1
if errorlevel 1 (
    echo 安装 requests...
    pip install requests
)

REM 启动服务
echo 启动企业微信应用机器人服务...
python scripts/start_wework_app_bot.py

pause