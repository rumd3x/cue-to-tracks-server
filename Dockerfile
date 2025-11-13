FROM python:3.12-slim

ENV THREADS=4
ENV PAIR_THREADS=2
ENV FORMAT=flac
ENV NO_CLEANUP=false

# Set UTF-8 locale to handle accented characters properly
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=utf-8

RUN apt-get update && apt-get install -y \
    ffmpeg cuetools shntool flac locales && \
    rm -rf /var/lib/apt/lists/*

# Install Python packages for character encoding detection
RUN pip install --no-cache-dir chardet

WORKDIR /app
COPY split_cue_server.py .

EXPOSE 8080
ENTRYPOINT ["python3", "split_cue_server.py"]
