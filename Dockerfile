FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/
COPY main.py .

# Persistent volumes are mounted at runtime — create directories so they exist
RUN mkdir -p output logs assets/audio assets/videos assets/temp assets/subtitles

# Drop root privileges
RUN useradd -m botuser
USER botuser

CMD ["python", "main.py"]
