#!/bin/sh

echo "=== Starting AI Music Telegram Bot Container ==="

# Trap signals for graceful shutdown (POSIX compliant: INT and TERM, NO 'SIG' prefix)
shutdown_handler() {
    echo "Shutting down background services..."
    if [ -n "$CELERY_PID" ]; then
        kill -TERM "$CELERY_PID" 2>/dev/null || true
    fi
    exit 0
}
trap shutdown_handler INT TERM

# 1. Wait for Database to become ready (up to 30-45s)
echo "[1/4] Checking database connection..."
python scripts/wait_for_db.py || true

# 2. Run Alembic database migrations
echo "[2/4] Applying database migrations..."
alembic upgrade head || echo "Alembic migration warning: continuing container startup..."

# 3. Start Celery AI audio worker in background
echo "[3/4] Starting Celery AI audio worker in background..."
celery -A app.workers.celery_app.celery_app worker \
    --loglevel=INFO \
    --concurrency=1 \
    -n railway_worker@%h &
CELERY_PID=$!

# 4. Start FastAPI Webhook API on assigned PORT
PORT="${PORT:-8000}"
echo "[4/4] Starting FastAPI Webhook API on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
