# =================================================================
# Production Dockerfile for AI Music Telegram Bot (Railway & Docker)
# =================================================================

FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

# Install system dependencies (FFmpeg, libsndfile, git, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application source code
COPY . .

# Create non-privileged user and setup storage directory permissions
RUN useradd -m -u 1000 appuser && \
    mkdir -p storage_data/uploads storage_data/stems storage_data/results storage_data/temp && \
    chmod +x scripts/entrypoint.sh && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Default entrypoint runs migrations, Celery worker, and FastAPI server
CMD ["./scripts/entrypoint.sh"]
