# Pipeline de processamento — Python + faster-whisper + ffmpeg (Etapa 2)
FROM python:3.11-slim

# ffmpeg: extração de frames de vídeo (RF-06) + extração de áudio para o Whisper.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# models/ (Whisper) e media/ são montados via volume (ver docker-compose.yml)
CMD ["python", "-m", "app.worker"]
