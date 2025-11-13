FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ffmpeg cuetools shntool flac && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY split_cue_server.py .

EXPOSE 8080
ENTRYPOINT ["python3", "split_cue_server.py"]
