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

import contextlib
import json
import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog

from src.config.settings import get_settings

if TYPE_CHECKING:
    from structlog.types import Processor


class _ResilientPrintLogger(structlog.PrintLogger):
    """``PrintLogger`` that drops a line it cannot write instead of raising.

    stdlib logging isolates sink failures in ``Handler.handleError``;
    ``PrintLogger`` prints straight to stdout, so a closed or broken stream
    (``OSError``) or one that cannot encode the line (``ValueError``)
    raised into the code that was logging, and a request whose work had
    committed came back as an error. The drop is reported on stderr as a
    JSON line, best effort. The notice names only the error type: the
    exception can hold the line itself (a ``UnicodeEncodeError`` carries
    the whole string), and the line can carry what the caller logged.
    """

    def msg(self, message: str) -> None:
        """Print *message*, or report on stderr that it was dropped."""
        try:
            super().msg(message)
        except (OSError, ValueError) as exc:
            notice = {
                "event": "Log line dropped",
                "level": "warning",
                "error_type": type(exc).__name__,
            }
            with contextlib.suppress(OSError, ValueError):
                print(json.dumps(notice), file=sys.stderr, flush=True)

    log = debug = info = warn = warning = msg
    fatal = failure = err = error = critical = exception = msg


def _resilient_print_logger(*_args: Any) -> _ResilientPrintLogger:
    """Logger factory for structlog: print to stdout, never raise on a failed write."""
    return _ResilientPrintLogger()


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
            # Structured tracebacks without frame locals: request bodies and
            # credentials live in locals, and ``dict_tracebacks`` renders them.
            structlog.processors.ExceptionRenderer(
                structlog.tracebacks.ExceptionDictTransformer(show_locals=False)
            ),
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
        logger_factory=_resilient_print_logger,
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
    logger: structlog.stdlib.BoundLogger = structlog.get_logger()
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger


__all__ = [
    "get_logger",
    "setup_logging",
]
