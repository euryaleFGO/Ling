@echo off
chcp 65001 >nul
echo ============================================================
echo TTS 模块依赖安装脚本
echo ============================================================
echo.
echo 显卡信息: NVIDIA GeForce RTX 2050 (4GB)
echo CUDA 版本: 12.4
echo Python 版本: 3.12
echo.
echo ============================================================
echo 步骤 1: 安装 PyTorch GPU 版本
echo ============================================================
echo.
echo 显卡: NVIDIA GeForce RTX 2050
echo CUDA: 12.4
echo Python: 3.12
echo.
echo 选项 A: 使用 CUDA 12.4 版本 (推荐)
echo    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
echo.
echo 选项 B: 使用 CUDA 12.1 版本 (兼容性更好)
echo    pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121
echo.
echo 正在安装 PyTorch 2.3.1 + CUDA 12.1 (推荐，兼容性更好)...
pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121
echo.

echo ============================================================
echo 步骤 2: 安装 ONNX Runtime
echo ============================================================
echo.
echo Windows 上安装 onnxruntime (支持 CPU)
echo 如果需要 GPU 支持，请手动安装 onnxruntime-gpu
echo.
pip install onnxruntime==1.18.0
echo.
echo 可选: 如果需要 GPU 支持，可以尝试:
echo   pip install onnxruntime-gpu==1.18.0
echo   注意: Windows 上可能需要特定配置
echo.

echo ============================================================
echo 步骤 3: 安装其他核心依赖
echo ============================================================
echo.
pip install numpy==1.26.4
pip install librosa==0.10.2
pip install soundfile==0.12.1
pip install conformer==0.3.2
pip install diffusers==0.29.0
pip install modelscope==1.20.0
pip install transformers==4.51.3
pip install onnx==1.16.0
echo.

echo ============================================================
echo 步骤 4: 安装其他依赖
echo ============================================================
echo.
echo 安装 YAML 相关依赖（注意版本兼容性）...
pip install ruamel.yaml==0.18.14
pip install ruamel.yaml.clib==0.2.12
pip install HyperPyYAML==1.2.2
echo.
pip install hydra-core==1.3.2
pip install omegaconf==2.3.0
pip install lightning==2.2.4
pip install pyworld==0.3.4
pip install rich==13.7.1
pip install gdown==5.1.0
pip install wget==3.2
pip install wetext==0.0.4
pip install openai-whisper==20231117
pip install tiktoken>=0.5.0
echo.
echo 注意: ttsfrd 是可选的，如果导入失败会使用 wetext 作为替代
echo.

echo ============================================================
echo 安装完成！
echo ============================================================
echo.
echo 接下来可以运行测试:
echo   python test_tts.py
echo.
pause

