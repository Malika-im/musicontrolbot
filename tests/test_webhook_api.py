"""
Tests for FastAPI Endpoints and Telegram Webhook.
"""

from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
import pytest

from app.core.config import get_settings
from app.database.connection import get_redis_client


def test_root_endpoint(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AI Music Telegram Bot"
    assert data["status"] == "running"


def test_health_check_endpoint(client: TestClient):
    # Mock Redis client dependency
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    client.app.dependency_overrides[get_redis_client] = lambda: mock_redis
    try:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["redis"] == "connected"
    finally:
        client.app.dependency_overrides.pop(get_redis_client, None)


def test_webhook_secret_verification(client: TestClient):
    settings = get_settings()
    secret_path = settings.webhook_path.split("/")[-1]

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    client.app.dependency_overrides[get_redis_client] = lambda: mock_redis

    update_payload = {
        "update_id": 999111,
        "message": {
            "message_id": 1,
            "chat": {"id": 12345},
            "from": {"id": 12345, "username": "testuser"},
            "text": "/start",
        },
    }

    try:
        # In production mode, invalid token returns 403
        settings.ENVIRONMENT = "production"
        resp_forbidden = client.post(
            f"/webhook/{secret_path}",
            json=update_payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret_token"},
        )
        assert resp_forbidden.status_code == 403

        # Valid secret token returns 200 OK
        resp_ok = client.post(
            f"/webhook/{secret_path}",
            json=update_payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": settings.TELEGRAM_WEBHOOK_SECRET},
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json() == {"ok": True}
    finally:
        settings.ENVIRONMENT = "test"
        client.app.dependency_overrides.pop(get_redis_client, None)


def test_webhook_update_deduplication(client: TestClient):
    """Test that Telegram update duplicates are discarded via Redis."""
    settings = get_settings()
    secret_path = settings.webhook_path.split("/")[-1]

    mock_redis = AsyncMock()
    # First call: is_new = True; Second call: is_new = False
    mock_redis.set = AsyncMock(side_effect=[True, False])
    client.app.dependency_overrides[get_redis_client] = lambda: mock_redis

    update_payload = {
        "update_id": 888777,
        "message": {
            "message_id": 2,
            "chat": {"id": 12345},
            "from": {"id": 12345, "username": "testuser"},
            "text": "/help",
        },
    }

    try:
        # First request
        resp1 = client.post(
            f"/webhook/{secret_path}",
            json=update_payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": settings.TELEGRAM_WEBHOOK_SECRET},
        )
        assert resp1.status_code == 200

        # Duplicate retry
        resp2 = client.post(
            f"/webhook/{secret_path}",
            json=update_payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": settings.TELEGRAM_WEBHOOK_SECRET},
        )
        assert resp2.status_code == 200
        assert resp2.json() == {"ok": True}
    finally:
        client.app.dependency_overrides.pop(get_redis_client, None)
