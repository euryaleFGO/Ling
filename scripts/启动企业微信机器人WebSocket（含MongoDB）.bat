@echo off
chcp 65001 >nul
title 企业微信机器人 WebSocket + MongoDB - 玲 (Liying)

echo ============================================================
echo    企业微信机器人 WebSocket + MongoDB - 玲 (Liying)
echo ============================================================
echo.

REM 检查 MongoDB 是否已经在运行
echo 检查 MongoDB 状态...
tasklist /FI "IMAGENAME eq mongod.exe" 2>NUL | find /I /N "mongod.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo ✅ MongoDB 已经在运行
) else (
    echo ⚠️  MongoDB 未运行，正在启动...
    
    REM 检查 MongoDB 路径
    if exist "E:\MongoDB\bin\mongod.exe" (
        echo 找到 MongoDB: E:\MongoDB\bin\mongod.exe
        
        REM 启动 MongoDB（后台运行）
        if exist "E:\MongoDB\mongod.cfg" (
            echo 使用配置文件启动 MongoDB...
            start "MongoDB" /MIN "E:\MongoDB\bin\mongod.exe" --config "E:\MongoDB\mongod.cfg"
        ) else (
            echo 使用默认配置启动 MongoDB...
            start "MongoDB" /MIN "E:\MongoDB\bin\mongod.exe" --dbpath "E:\MongoDB\data"
        )
        
        echo 等待 MongoDB 启动...
        timeout /t 3 /nobreak >nul
        
        REM 再次检查
        tasklist /FI "IMAGENAME eq mongod.exe" 2>NUL | find /I /N "mongod.exe">NUL
        if "%ERRORLEVEL%"=="0" (
            echo ✅ MongoDB 启动成功
        ) else (
            echo ❌ MongoDB 启动失败
            echo 请手动启动 MongoDB 或检查配置
            pause
            exit /b 1
        )
    ) else (
        echo ❌ 错误: 找不到 MongoDB
        echo 请检查路径: E:\MongoDB\bin\mongod.exe
        echo 或手动启动 MongoDB
        pause
        exit /b 1
    )
)

echo.
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
