"""
Application Configuration Module using Pydantic Settings.
Loads and validates settings from environment variables and .env file.
Includes native support for Railway, Render, and standard cloud providers.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Project metadata ---
    PROJECT_NAME: str = "AI Music Telegram Bot"
    PROJECT_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "production", "test"] = "production"
    DEBUG: bool = False
    SECRET_KEY: str = "dev_secret_key_please_change_in_production"

    # --- Server Settings ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = Field(default=8000, alias="PORT")

    # --- Telegram Settings ---
    TELEGRAM_BOT_TOKEN: str = Field(
        default="mock_token_for_testing",
        description="Telegram Bot API Token from @BotFather",
    )
    TELEGRAM_WEBHOOK_URL: str = Field(
        default="http://localhost:8000",
        description="Public HTTPS URL for Telegram Webhook",
    )
    TELEGRAM_WEBHOOK_SECRET: str = Field(
        default="webhook_secret_key_change_me",
        description="Secret token passed in X-Telegram-Bot-Api-Secret-Token",
    )

    # --- Database Settings ---
    POSTGRES_USER: str = "aimusic"
    POSTGRES_PASSWORD: str = "aimusic_secure_password"
    POSTGRES_DB: str = "aimusic_db"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+asyncpg://aimusic:aimusic_secure_password@postgres:5432/aimusic_db"
    DATABASE_SYNC_URL: str = "postgresql+psycopg2://aimusic:aimusic_secure_password@postgres:5432/aimusic_db"

    # --- Redis & Celery ---
    REDIS_URL: Optional[str] = None
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    # --- Storage & Limits ---
    STORAGE_BASE_DIR: Path = Path("./storage_data")
    MAX_FILE_SIZE_MB: int = 50
    MAX_DURATION_SECONDS: int = 900  # 15 minutes
    CLEANUP_RETENTION_HOURS: int = 24
    DISK_MIN_FREE_SPACE_GB: float = 2.0

    # --- User & Task Limits ---
    MAX_CONCURRENT_TASKS_PER_USER: int = 2
    PROCESSING_TIMEOUT_SECONDS: int = 600

    # --- AI & Hardware Acceleration ---
    DEVICE: Literal["cuda", "cpu", "mps"] = "cpu"
    DEMUCS_MODEL: str = "htdemucs"
    WHISPER_MODEL: str = "base"
    WHISPER_COMPUTE_TYPE: str = "float32"

    # --- LLM Settings ---
    LLM_PROVIDER: Literal["heuristic", "openai", "gemini"] = "heuristic"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """
        Normalize cloud database URLs (Railway, Render, Heroku).
        Converts postgres:// and postgresql:// to postgresql+asyncpg://
        Auto-detects Railway's DATABASE_PUBLIC_URL or PGHOST if default is unchanged.
        """
        # If default placeholder or empty, look for Railway alternative environment variables
        if not v or "aimusic:aimusic_secure_password@postgres:5432" in v:
            alt_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
            if not alt_url and os.environ.get("PGHOST"):
                user = os.environ.get("PGUSER", "postgres")
                pwd = os.environ.get("PGPASSWORD", "")
                host = os.environ.get("PGHOST", "")
                port = os.environ.get("PGPORT", "5432")
                db = os.environ.get("PGDATABASE", "railway")
                alt_url = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
            if alt_url:
                v = alt_url

        if not v:
            return v

        # Fix scheme for asyncpg
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)

        # Remove sslmode query parameter if present, as asyncpg handles SSL directly
        if "?" in v and "sslmode=" in v:
            import re
            v = re.sub(r"[?&]sslmode=[^&]+", "", v)
            if v.endswith("?"):
                v = v[:-1]

        return v

    @field_validator("DATABASE_SYNC_URL", mode="before")
    @classmethod
    def normalize_sync_database_url(cls, v: str, info) -> str:
        """Derive or normalize sync database URL for Alembic."""
        if v:
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+psycopg2://", 1)
            if v.startswith("postgresql://") and not v.startswith("postgresql+"):
                return v.replace("postgresql://", "postgresql+psycopg2://", 1)
            return v
        return v

    def model_post_init(self, __context) -> None:
        """Post-initialization adjustments for Railway & Cloud deployment."""
        # Auto-configure sync URL if needed
        if "postgresql+asyncpg://" in self.DATABASE_URL and "sqlite" not in self.DATABASE_SYNC_URL:
            self.DATABASE_SYNC_URL = self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)

        # Auto-configure from REDIS_URL or REDIS_PUBLIC_URL or REDISHOST (provided by Railway)
        redis_target = self.REDIS_URL or os.environ.get("REDIS_URL") or os.environ.get("REDIS_PUBLIC_URL")
        if not redis_target and os.environ.get("REDISHOST"):
            r_host = os.environ.get("REDISHOST")
            r_port = os.environ.get("REDISPORT", "6379")
            r_pwd = os.environ.get("REDISPASSWORD", "")
            r_user = os.environ.get("REDISUSER", "default")
            redis_target = f"redis://{r_user}:{r_pwd}@{r_host}:{r_port}/0"

        if redis_target:
            self.REDIS_URL = redis_target
            self.CELERY_BROKER_URL = redis_target
            self.CELERY_RESULT_BACKEND = redis_target

        # Auto-configure Webhook URL if RAILWAY_PUBLIC_DOMAIN is available
        railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        if railway_domain and (not self.TELEGRAM_WEBHOOK_URL or "localhost" in self.TELEGRAM_WEBHOOK_URL):
            self.TELEGRAM_WEBHOOK_URL = f"https://{railway_domain}"

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def uploads_dir(self) -> Path:
        return self.STORAGE_BASE_DIR / "uploads"

    @property
    def stems_dir(self) -> Path:
        return self.STORAGE_BASE_DIR / "stems"

    @property
    def results_dir(self) -> Path:
        return self.STORAGE_BASE_DIR / "results"

    @property
    def temp_dir(self) -> Path:
        return self.STORAGE_BASE_DIR / "temp"

    @property
    def webhook_path(self) -> str:
        token_hash = hash(self.TELEGRAM_BOT_TOKEN)
        return f"/webhook/{abs(token_hash)}"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
