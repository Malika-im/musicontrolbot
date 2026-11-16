"""
FastAPI Routes.
Root, Health checks, and Telegram Webhook endpoint with deduplication.
"""

import asyncio
from typing import Any, Dict
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_telegram_webhook_header
from app.bot.bot_service import TelegramBotService
from app.bot.dispatcher import TelegramDispatcher
from app.core.config import get_settings
from app.core.logging import logger
from app.database.connection import get_db_session, get_redis_client

router = APIRouter()


@router.get("/", tags=["Info"])
async def root() -> Dict[str, Any]:
    """Root endpoint with service information."""
    settings = get_settings()
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
        },
    }


@router.get("/health", tags=["Health"])
async def health_check(
    db: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis_client),
) -> Dict[str, Any]:
    """
    Health check endpoint verifying PostgreSQL and Redis connections.
    Returns 200 OK if all systems are healthy, 503 if any dependency is down.
    """
    settings = get_settings()
    health_status: Dict[str, Any] = {
        "status": "healthy",
        "version": settings.PROJECT_VERSION,
        "database": "unknown",
        "redis": "unknown",
    }

    # Verify Database
    try:
        await db.execute(text("SELECT 1"))
        health_status["database"] = "connected"
    except Exception as e:
        logger.error(f"Health check DB error: {e}")
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # Verify Redis
    try:
        await redis.ping()
        health_status["redis"] = "connected"
    except Exception as e:
        logger.error(f"Health check Redis error: {e}")
        health_status["redis"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    if health_status["status"] != "healthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=health_status,
        )

    return health_status


async def _process_telegram_update_background(update: Dict[str, Any]) -> None:
    """Execute update dispatching in a background task."""
    from app.database.connection import get_session_factory
    session_factory = get_session_factory()
    bot_service = TelegramBotService()

    async with session_factory() as session:
        try:
            dispatcher = TelegramDispatcher(session, bot_service)
            await dispatcher.dispatch_update(update)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(f"Unhandled error in Telegram update processing: {e}")


@router.post(
    "/webhook/{secret_path}",
    tags=["Telegram"],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_telegram_webhook_header)],
)
async def telegram_webhook(
    secret_path: str,
    update: Dict[str, Any],
    background_tasks: BackgroundTasks,
    redis: aioredis.Redis = Depends(get_redis_client),
) -> Dict[str, bool]:
    """
    Telegram Webhook endpoint.
    Fast non-blocking handler with update deduplication.
    """
    settings = get_settings()
    expected_path = settings.webhook_path.split("/")[-1]

    # Validate secret path
    if secret_path != expected_path and settings.ENVIRONMENT != "test":
        logger.warning(f"Rejected webhook with invalid secret_path: {secret_path}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    update_id = update.get("update_id")
    if update_id is not None:
        # Deduplication check via Redis (24-hour expiration)
        dedup_key = f"tg_update_dedup:{update_id}"
        try:
            is_new = await redis.set(dedup_key, "1", ex=86400, nx=True)
            if not is_new:
                logger.info(f"Duplicate Telegram update received: {update_id}, skipping.")
                return {"ok": True}
        except Exception as e:
            logger.warning(f"Redis dedup check error (proceeding anyway): {e}")

    # Enqueue background task so webhook responds immediately to Telegram
    background_tasks.add_task(_process_telegram_update_background, update)

    return {"ok": True}
