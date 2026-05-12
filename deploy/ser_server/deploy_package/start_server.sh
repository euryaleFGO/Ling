#!/bin/bash
echo "SER 情绪识别服务器"
echo "检查依赖..."
pip install flask flask-cors transformers torch numpy 2>/dev/null
echo "启动服务器（端口 5003）..."
python3 server.py --port 5003 --device cuda:0
