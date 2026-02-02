"""Logging configuration using structlog.

Provides structured logging with:
- Pretty console output in development (colorized, readable)
- JSON output in production (machine-parseable)
- Request ID tracking
- Automatic context binding

Usage:
    from src.config.logging import get_logger

    logger = get_logger()
    logger.info("User logged in", user_id="123", action="login")

With context:
    logger = get_logger().bind(request_id="req_abc123")
    logger.info("Processing request")  # Includes request_id automatically
"""

import logging
from typing import TYPE_CHECKING, Any

import structlog

from src.config.settings import get_settings

if TYPE_CHECKING:
    from structlog.types import Processor


def _setup_structlog(*, json_logs: bool, log_level: str) -> None:
    """Configure structlog with appropriate processors.

    Args:
        json_logs: If True, output JSON. If False, pretty console output.
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if json_logs:
        # Production: JSON output for log aggregators
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Pretty, colorized console output
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def setup_logging() -> None:
    """Initialize logging configuration based on settings.

    Call this once at application startup (in main.py).
    """
    settings = get_settings()

    # Use JSON in production, pretty output in development
    json_logs = settings.is_production

    _setup_structlog(
        json_logs=json_logs,
        log_level=settings.log_level,
    )


def get_logger(**initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Get a configured logger instance.

    Args:
        **initial_context: Optional key-value pairs to bind to the logger.

    Returns:
        A bound logger instance.

    Example:
        >>> logger = get_logger(service="media")
        >>> logger.info("Starting scan", directory="/media/movies")
    """
    logger = structlog.get_logger()
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger


__all__ = [
    "get_logger",
    "setup_logging",
]
