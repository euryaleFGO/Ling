FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . /app

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r deploy/asr_server/requirements.txt

# 创建日志目录
RUN mkdir -p /app/deploy/asr_server/logs

# 暴露端口
EXPOSE 5002

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV FUNASR_CACHE_DIR=/app/.cache/funasr

# 启动服务器
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5002", "--timeout", "300", "--chdir", "/app/deploy/asr_server", "server:app"]
