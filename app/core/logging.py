"""
Structured Logging Configuration.
"""

import logging
import sys
from app.core.config import get_settings


def setup_logging() -> None:
    """Configure root and application loggers."""
    settings = get_settings()
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    logging_format = (
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s"
    )

    logging.basicConfig(
        level=log_level,
        format=logging_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    # Silence noisy external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


logger = logging.getLogger("ai_music_bot")
