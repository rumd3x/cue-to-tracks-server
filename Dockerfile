FROM python:3.12-slim

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=utf-8

ENV THREADS=4
ENV PAIR_THREADS=2
ENV FORMAT=flac
ENV NO_CLEANUP=false

RUN apt-get update && apt-get install -y \
    ffmpeg cuetools shntool flac locales && \
    rm -rf /var/lib/apt/lists/*

COPY . /app
RUN pip install -r requirements.txt

EXPOSE 8080
ENTRYPOINT ["python3", "/app/split_cue_server.py"]
