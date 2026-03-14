#!/bin/bash
# TTS 服务启动脚本

# 配置
HOST=${TTS_HOST:-0.0.0.0}
PORT=${TTS_PORT:-5001}
MODEL_PATH=${COSYVOICE_MODEL_PATH:-./models/TTS/CosyVoice2-0.5B}

echo "========================================"
echo "  TTS 云端服务"
echo "  地址: http://$HOST:$PORT"
echo "  模型: $MODEL_PATH"
echo "========================================"

# 检查模型是否存在
if [ ! -d "$MODEL_PATH" ]; then
    echo "[错误] 模型目录不存在: $MODEL_PATH"
    echo "请先下载模型:"
    echo "  python -c \"from modelscope import snapshot_download; snapshot_download('iic/CosyVoice2-0.5B', local_dir='$MODEL_PATH')\""
    exit 1
fi

# 启动服务
export COSYVOICE_MODEL_PATH=$MODEL_PATH
python service.py --host $HOST --port $PORT
