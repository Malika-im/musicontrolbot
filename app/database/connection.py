"""
Database and Redis connection management.
Supports async PostgreSQL via asyncpg and Redis connection pooling.
"""

from typing import AsyncGenerator
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import get_settings
from app.core.logging import logger

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_redis_pool: aioredis.Redis | None = None


def get_engine() -> AsyncEngine:
    """Get or create singleton AsyncEngine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        is_sqlite = settings.DATABASE_URL.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}

        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        logger.info(f"Initialized Database Engine ({settings.DATABASE_URL.split('@')[-1]})")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create singleton async sessionmaker."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for yielding database sessions."""
    session_maker = get_session_factory()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_redis_client() -> aioredis.Redis:
    """Get or create singleton async Redis client."""
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        if settings.REDIS_URL:
            _redis_pool = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
        else:
            _redis_pool = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD or None,
                decode_responses=True,
            )
    return _redis_pool


async def close_connections() -> None:
    """Close DB engine and Redis pool cleanly on shutdown."""
    global _engine, _session_factory, _redis_pool
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Closed database connection pool")
    if _redis_pool is not None:
        if hasattr(_redis_pool, "aclose"):
            await _redis_pool.aclose()
        else:
            await _redis_pool.close()
        _redis_pool = None
        logger.info("Closed Redis connection")
