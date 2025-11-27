FROM python:3.12-slim

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=utf-8

ENV THREADS=4
ENV PAIR_THREADS=2
ENV FORMAT=flac
ENV NO_CLEANUP=false
ENV CUE_SPLITTER_DB=/data/cue_splitter_jobs.db

RUN apt-get update && apt-get install -y \
    ffmpeg cuetools shntool flac locales && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY main.py .

# Create data directory for database persistence
RUN mkdir -p /data

VOLUME ["/data"]

EXPOSE 8080
ENTRYPOINT ["python3", "/app/main.py"]
