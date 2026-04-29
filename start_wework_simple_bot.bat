@echo off
chcp 65001 >nul
echo ============================================================
echo         Enterprise WeChat Bot - Liying
echo              Simplified Version
echo ============================================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found, please install Python first
    pause
    exit /b 1
)

REM Check dependencies
echo Checking dependencies...
pip show flask >nul 2>&1
if errorlevel 1 (
    echo Installing Flask...
    pip install flask
)

pip show requests >nul 2>&1
if errorlevel 1 (
    echo Installing requests...
    pip install requests
)

REM Start service
echo Starting Enterprise WeChat Bot Service (Simplified Version)...
python scripts/start_wework_simple_bot.py

pause