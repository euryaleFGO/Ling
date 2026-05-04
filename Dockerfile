FROM python:3.12-slim AS base

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[tts,asr]" 2>/dev/null || \
    pip install --no-cache-dir openai pydantic python-dotenv pymongo numpy \
    requests flask flask-cors websockets Pillow edge-tts sounddevice

# Copy application
COPY src/ src/
COPY config/ config/
COPY main.py .

EXPOSE 5001 8765

CMD ["python", "main.py"]
