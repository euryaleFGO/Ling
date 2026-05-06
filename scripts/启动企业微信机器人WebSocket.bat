@echo off
chcp 65001 >nul
title 企业微信机器人 WebSocket 长连接版本 - 玲 (Liying)

echo ============================================================
echo    企业微信机器人 WebSocket 长连接版本 - 玲 (Liying)
echo ============================================================
echo.

REM 激活 conda 环境
echo 正在激活 conda 环境...
call F:\envs\Liying\Scripts\activate.bat
if errorlevel 1 (
    echo 错误: 无法激活 conda 环境
    echo 请检查路径: F:\envs\Liying
    pause
    exit /b 1
)

echo.
echo 正在启动企业微信机器人 WebSocket 服务...
echo.

REM 启动 WebSocket 机器人
F:\envs\Liying\python.exe scripts\start_wework_bot_websocket.py

if errorlevel 1 (
    echo.
    echo 错误: 机器人启动失败
    echo 请检查配置和日志
    pause
    exit /b 1
)

pause
