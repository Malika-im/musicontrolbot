"""
API Dependencies.
Database sessions, Redis clients, and authentication checks.
"""

from typing import AsyncGenerator
from fastapi import Header, HTTPException, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import verify_webhook_secret
from app.database.connection import get_db_session, get_redis_client


async def verify_telegram_webhook_header(
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> None:
    """Validate X-Telegram-Bot-Api-Secret-Token header."""
    settings = get_settings()
    # In test environments or when secret not enforced, allow pass
    if settings.ENVIRONMENT == "test":
        return

    if not verify_webhook_secret(x_telegram_bot_api_secret_token, settings.TELEGRAM_WEBHOOK_SECRET):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing Telegram webhook secret token",
        )
