"""
Wait for database script.
Ensures PostgreSQL is ready and accepting connections before running migrations and starting services.
Prevents startup crashes on Railway, Docker, and Kubernetes.
"""

import os
import sys
import time
import socket
from urllib.parse import urlparse

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import get_settings


def wait_for_postgres(max_attempts: int = 15, delay_seconds: float = 1.0) -> bool:
    settings = get_settings()
    db_url = settings.DATABASE_URL

    if "sqlite" in db_url:
        print("[wait_for_db] Using SQLite, no network wait required.")
        return True

    # Parse host and port
    clean_url = db_url.replace("postgresql+asyncpg://", "http://").replace("postgresql+psycopg2://", "http://").replace("postgresql://", "http://")
    parsed = urlparse(clean_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432

    print(f"[wait_for_db] Checking PostgreSQL connectivity at {host}:{port}...")

    for attempt in range(1, max_attempts + 1):
        try:
            with socket.create_connection((host, port), timeout=2.0):
                print(f"[wait_for_db] [Attempt {attempt}/{max_attempts}] Socket connection to {host}:{port} successful!")
                time.sleep(0.5)
                print("[wait_for_db] Database is ready and accepting connections.")
                return True
        except (socket.timeout, ConnectionRefusedError, socket.gaierror, OSError) as exc:
            print(f"[wait_for_db] [Attempt {attempt}/{max_attempts}] Waiting for PostgreSQL at {host}:{port}...")
            time.sleep(delay_seconds)

    print(f"\n[wait_for_db] WARNING: Could not connect to PostgreSQL at {host}:{port} after {max_attempts * delay_seconds:.0f} seconds.")
    print("[wait_for_db] If deploying on Railway, please ensure:")
    print("  1. A PostgreSQL service is added to your Railway project.")
    print("  2. In your bot service -> 'Variables' -> add 'DATABASE_URL' reference (e.g. ${{Postgres.DATABASE_URL}}).")
    print("[wait_for_db] Continuing container startup so API can report status via /health.\n")
    return False


if __name__ == "__main__":
    wait_for_postgres()
