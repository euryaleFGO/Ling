# 测试修复脚本
# 用法: .\test_fixes.ps1

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "  测试异步对话系统修复" -ForegroundColor Yellow
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host ""

# 检查 Python 环境
Write-Host "[1/5] 检查 Python 环境..." -ForegroundColor Green
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Python: $pythonVersion" -ForegroundColor Gray
} else {
    Write-Host "  ✗ Python 未找到" -ForegroundColor Red
    exit 1
}

# 检查虚拟环境
Write-Host "[2/5] 检查虚拟环境..." -ForegroundColor Green
if ($env:VIRTUAL_ENV) {
    Write-Host "  ✓ 虚拟环境: $env:VIRTUAL_ENV" -ForegroundColor Gray
} else {
    Write-Host "  ⚠ 未激活虚拟环境（可能需要运行 conda activate liying）" -ForegroundColor Yellow
}

# 检查配置文件
Write-Host "[3/5] 检查配置文件..." -ForegroundColor Green
$configFiles = @(
    "config/interrupt_config.json",
    ".env"
)
foreach ($file in $configFiles) {
    if (Test-Path $file) {
        Write-Host "  ✓ $file" -ForegroundColor Gray
    } else {
        Write-Host "  ✗ $file 不存在" -ForegroundColor Red
    }
}

# 检查远程服务配置
Write-Host "[4/5] 检查服务配置..." -ForegroundColor Green
$envContent = Get-Content .env -Raw
if ($envContent -match "LIYING_TTS_REMOTE_URL=http") {
    $ttsUrl = ($envContent | Select-String "LIYING_TTS_REMOTE_URL=(.+)" | ForEach-Object { $_.Matches.Groups[1].Value }).Trim()
    Write-Host "  ⚠ 配置了远程 TTS 服务: $ttsUrl" -ForegroundColor Yellow
    Write-Host "    如果服务未运行，建议注释掉此行以使用本地模型" -ForegroundColor Yellow
} else {
    Write-Host "  ✓ 使用本地 TTS 模型" -ForegroundColor Gray
}

if ($envContent -match "LIYING_ASR_REMOTE_URL=http") {
    $asrUrl = ($envContent | Select-String "LIYING_ASR_REMOTE_URL=(.+)" | ForEach-Object { $_.Matches.Groups[1].Value }).Trim()
    Write-Host "  ⚠ 配置了远程 ASR 服务: $asrUrl" -ForegroundColor Yellow
    Write-Host "    如果服务未运行，建议注释掉此行以使用本地模型" -ForegroundColor Yellow
} else {
    Write-Host "  ✓ 使用本地 ASR 模型" -ForegroundColor Gray
}

# 检查 MongoDB
Write-Host "[5/5] 检查 MongoDB..." -ForegroundColor Green
$mongoProcess = Get-Process -Name mongod -ErrorAction SilentlyContinue
if ($mongoProcess) {
    Write-Host "  ✓ MongoDB 正在运行 (PID: $($mongoProcess.Id))" -ForegroundColor Gray
} else {
    Write-Host "  ⚠ MongoDB 未运行（程序会尝试自动启动）" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "  准备启动程序" -ForegroundColor Yellow
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host ""

# 询问是否启动
$response = Read-Host "是否启动程序？(y/n)"
if ($response -eq 'y' -or $response -eq 'Y') {
    Write-Host ""
    Write-Host "启动中..." -ForegroundColor Green
    Write-Host "提示：输入 'quit' 退出程序" -ForegroundColor Gray
    Write-Host ""
    python main.py --text-gui
} else {
    Write-Host ""
    Write-Host "已取消。你可以手动运行：python main.py --text-gui" -ForegroundColor Gray
}
