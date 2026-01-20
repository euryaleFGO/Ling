模型文件目录说明
================

此目录用于存放模型文件，由于模型文件较大，不会上传到Git仓库。

目录结构：
----------
models/
├── embedding/          # 文本嵌入模型
│   └── all-MiniLM-L6-v2/  # Sentence Transformers 嵌入模型
└── TTS/                # 语音合成模型
    └── CosyVoice2-0.5B/    # CosyVoice2 TTS 模型

模型下载方式：
------------

1. Embedding 模型 (all-MiniLM-L6-v2)
   - 模型会自动从 HuggingFace 下载
   - 或手动下载：https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2

2. TTS 模型 (CosyVoice2-0.5B)
   使用 ModelScope 下载：
   ```python
   from modelscope import snapshot_download
   snapshot_download('iic/CosyVoice2-0.5B', local_dir='backtend/models/TTS/CosyVoice2-0.5B')
   ```

3. 参考音频文件
   - 将参考音频文件（.wav格式）放在项目根目录的 Model/ 文件夹下
   - 文件名建议使用有意义的名称，如：reference_voice.wav

注意事项：
---------
- 模型文件较大，请确保有足够的磁盘空间
- 首次运行时会自动下载模型（如果配置了自动下载）
- 建议使用 ModelScope 或 HuggingFace 的镜像站点加速下载
