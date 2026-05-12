@echo off
chcp 65001 >nul
echo ============================================================
echo   SER 情绪识别服务器
echo ============================================================
echo.
python -c "import flask" 2>nul
if %errorlevel% neq 0 (
    echo [!] 缺少依赖，正在安装...
    pip install flask flask-cors transformers torch numpy
)
echo 启动服务器（端口 5003）...
python server.py --port 5003 --device cuda:0
pause
