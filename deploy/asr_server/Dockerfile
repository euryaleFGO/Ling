FROM python:3.10-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libsndfile1 ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code (self-contained, no project dependency)
COPY server.py .

# Optional: pre-download models (uncomment to bake into image)
# RUN python -c "\
# from funasr import AutoModel; \
# AutoModel(model='paraformer-zh-streaming', device='cpu'); \
# AutoModel(model='fsmn-vad', device='cpu')"

RUN mkdir -p /app/logs

EXPOSE 5002

ENV PYTHONUNBUFFERED=1
ENV ASR_DEVICE=auto
ENV ASR_HOST=0.0.0.0
ENV ASR_PORT=5002

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5002", "--timeout", "300", "server:app"]
