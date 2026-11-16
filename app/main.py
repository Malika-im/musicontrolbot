"""
FastAPI Main Application Entry Point.
Initializes application, lifespan events, middleware, and routing.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.bot.bot_service import TelegramBotService
from app.core.config import get_settings
from app.core.exceptions import MusicBotException
from app.core.logging import logger, setup_logging
from app.database.connection import close_connections, get_engine
from app.database.models import Base
from app.storage.storage_service import StorageService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    setup_logging()
    settings = get_settings()
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.PROJECT_VERSION} [{settings.ENVIRONMENT}]")

    # 1. Ensure storage directories exist
    storage = StorageService()
    storage.ensure_directories()

    # 2. Initialize database tables if in development/test
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema validated/created.")
    except Exception as e:
        logger.warning(f"Database table verification deferred: {e}")

    # 3. Register Telegram Webhook if configured and in production
    if settings.ENVIRONMENT == "production" and "mock" not in settings.TELEGRAM_BOT_TOKEN:
        try:
            bot = TelegramBotService()
            full_webhook_url = f"{settings.TELEGRAM_WEBHOOK_URL}{settings.webhook_path}"
            logger.info(f"Registering Telegram webhook at {full_webhook_url}")
            await bot.set_webhook(full_webhook_url, settings.TELEGRAM_WEBHOOK_SECRET)
        except Exception as e:
            logger.error(f"Failed to auto-register Telegram webhook: {e}")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    await close_connections()
    logger.info("Application shutdown complete.")


def create_application() -> FastAPI:
    """Factory function to build FastAPI app."""
    settings = get_settings()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        description="AI Telegram Bot for music vocal extraction, backing track creation, stem separation, and pitch shifting.",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # Global domain exception handler
    @app.exception_handler(MusicBotException)
    async def music_bot_exception_handler(request: Request, exc: MusicBotException):
        logger.warning(f"Domain exception on {request.url.path}: {exc.message}")
        return JSONResponse(
            status_code=400,
            content={"error": exc.message, "user_friendly_message": exc.user_friendly_message},
        )

    app.include_router(router)
    return app


app = create_application()
