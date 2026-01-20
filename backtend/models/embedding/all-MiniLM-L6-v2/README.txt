all-MiniLM-L6-v2 嵌入模型目录
=============================

此目录用于存放 Sentence Transformers 的 all-MiniLM-L6-v2 嵌入模型。

模型下载：
---------
模型会在首次使用时自动从 HuggingFace 下载，或手动下载：

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
# 模型会自动下载到缓存目录
```

模型文件说明：
-------------
下载完成后，此目录应包含以下文件：
- config.json
- pytorch_model.bin 或 model.safetensors
- tokenizer.json
- vocab.txt
- 其他必要的配置文件

注意事项：
---------
- 模型文件会自动缓存到 HuggingFace 的默认缓存目录
- 如果需要指定本地目录，请修改代码中的模型路径配置
