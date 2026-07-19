# opusfree — container image for web hosting (Hugging Face Spaces, Render, Fly.io…)
# Bakes in ffmpeg so no host setup is needed. Serves the web UI on $PORT.
FROM python:3.11-slim

# ffmpeg + ffprobe for probing/encoding; libgl/libglib for OpenCV runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces sends traffic to 7860; other hosts set $PORT themselves.
ENV HOST=0.0.0.0 PORT=7860 \
    HF_HOME=/tmp/hf XDG_CACHE_HOME=/tmp/cache
EXPOSE 7860

CMD ["python", "webrun.py"]
