#!/bin/sh
set -e

echo "=== Starting AI Music Telegram Bot Container ==="

# 1. Apply database migrations
echo "[1/3] Running database migrations with Alembic..."
alembic upgrade head || echo "Alembic migration warning: proceeding with startup..."

# 2. Start Celery worker in background
echo "[2/3] Starting Celery AI audio worker in background..."
celery -A app.workers.celery_app.celery_app worker \
    --loglevel=INFO \
    --concurrency=1 \
    -n railway_worker@%h &
CELERY_PID=$!

# Trap signals for graceful shutdown
trap "kill -TERM $CELERY_PID" SIGINT SIGTERM

# 3. Start FastAPI with Uvicorn
PORT="${PORT:-8000}"
echo "[3/3] Starting FastAPI Webhook API on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
