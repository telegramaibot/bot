"""Loguru logger configuration helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from userbot_remote.config.settings import Settings


def setup_logger(settings: Settings) -> None:
    """Configure structured logging for console and file output.

    Args:
        settings: Validated application settings.
    """

    log_file = Path(settings.log_dir) / "userbot_remote.log"
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    )
    logger.add(
        log_file,
        level=settings.log_level,
        enqueue=True,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        backtrace=False,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )


__all__ = ["logger", "setup_logger"]
