CosyVoice2-0.5B 模型目录
========================

此目录用于存放 CosyVoice2-0.5B TTS 模型文件。

模型下载：
---------
使用 ModelScope 下载：

```python
from modelscope import snapshot_download
snapshot_download('iic/CosyVoice2-0.5B', local_dir='backtend/models/TTS/CosyVoice2-0.5B')
```

或者在项目根目录执行：

```bash
python -c "from modelscope import snapshot_download; snapshot_download('iic/CosyVoice2-0.5B', local_dir='backtend/models/TTS/CosyVoice2-0.5B')"
```

模型文件说明：
-------------
下载完成后，此目录应包含以下文件：
- 模型权重文件（.pt, .pth）
- 配置文件（.json, .yaml）
- ONNX 模型文件（.onnx）
- 其他必要的模型文件

注意事项：
---------
- 模型文件较大（约几百MB到几GB），不会上传到Git仓库
- 首次使用前需要先下载模型
- 确保有足够的磁盘空间和显存（推荐4GB+显存）
