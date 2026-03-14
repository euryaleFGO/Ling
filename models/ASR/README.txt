ASR 模型目录
=============

请下载以下模型到此目录：

1. paraformer-zh-streaming (流式 ASR 模型, ~880MB)
   下载命令:
   git lfs install
   git clone https://huggingface.co/funasr/paraformer-zh-streaming

2. fsmn-vad (VAD 模型, ~1.6MB)
   下载命令:
   git clone https://huggingface.co/funasr/fsmn-vad

下载完成后目录结构:
models/ASR/
├── paraformer-zh-streaming/
│   ├── model.onnx
│   ├── decoder.onnx
│   ├── config.yaml
│   ├── am.mvn
│   └── tokens.json
└── fsmn-vad/
    ├── model.onnx
    ├── config.yaml
    └── am.mvn
