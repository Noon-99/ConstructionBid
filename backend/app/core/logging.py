"""Structured logging configuration."""

import sys
from typing import Any

from loguru import logger

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure loguru with JSON or text formatting."""
    logger.remove()  # Remove default handler

    if settings.log_format == "json":
        logger.add(
            sys.stdout,
            format="{time} | {level} | {name}:{function}:{line} | {message}",
            serialize=True,
            level=settings.log_level,
        )
    else:
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=settings.log_level,
            colorize=True,
        )


def get_logger(name: str) -> Any:
    """Get a logger instance for a module."""
    return logger.bind(name=name)

