"""Global exception-to-HTTP translation.

Centralises how domain, application, and infrastructure exceptions
surface to API clients. Routes raise typed exceptions; these handlers
translate them into the v3.0 error envelope without every controller
repeating the mapping.

Handlers are intentionally narrow — each knows only how to log and
serialize a category of errors. The envelope format comes from
``CoreException.to_dict()`` so the contract stays in one place.
"""

from typing import Any, cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from src.building_blocks.domain.errors import CoreException, Severity
from src.building_blocks.presentation.error_mapping import (
    resolve_error_type,
    resolve_http_status,
)
from src.config.logging import get_logger

# Keys a caller may supply via ``HTTPException(detail={...})`` — everything
# else is dropped so an attacker-controlled or typo'd dict can't reshape
# the envelope (e.g. override the computed ``type``).
_ALLOWED_DETAIL_KEYS = frozenset({"message", "code", "param", "details"})


async def core_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate typed domain/application/infra exceptions into HTTP.

    HTTP status and error ``type`` are resolved through the registry
    (ADR-012) keyed by ``exc.code``, not from the exception class —
    domain code carries no HTTP knowledge. ``CoreException.to_dict()``
    returns the body without ``type``; this handler prepends the
    registry-resolved value so the JSON output keeps the v3 envelope
    key order (type, message, code, …). ``_internal`` is never
    serialized.

    Logging level is chosen from ``exc.severity`` so a 4xx doesn't look
    like a 5xx in the logs.

    The ``Exception`` parameter type matches FastAPI's handler protocol;
    registration in ``register_exception_handlers`` guarantees this
    handler only receives ``CoreException`` instances, so we narrow via
    ``cast`` instead of a runtime check.
    """
    exc = cast(CoreException, exc)
    http_status = resolve_http_status(exc.code)
    error_type = resolve_error_type(http_status)

    logger = get_logger().bind(
        exception_id=exc.exception_id,
        code=exc.code,
        http_status=http_status,
        path=request.url.path,
    )
    _log_with_severity(logger, exc)

    content = {"type": error_type, **exc.to_dict()}
    return JSONResponse(status_code=http_status, content=content)


async def request_validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Format FastAPI/Pydantic request validation errors in v3 shape."""
    exc = cast(RequestValidationError, exc)
    errors = [
        {
            "field": ".".join(str(loc) for loc in err.get("loc", ())[1:]),
            "message": err.get("msg", "Validation error"),
            "code": err.get("type", "validation_error"),
        }
        for err in exc.errors()
    ]
    get_logger().info(
        "Request validation failed",
        path=request.url.path,
        error_count=len(errors),
    )
    return JSONResponse(
        status_code=422,
        content={
            "type": "validation_error",
            "message": "Invalid request payload",
            "code": "REQUEST_VALIDATION_ERROR",
            "details": errors,
        },
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate Starlette/FastAPI ``HTTPException`` into the envelope.

    Routes occasionally raise ``HTTPException`` (e.g. 404 from path
    mismatches or ``Response(404)`` shortcuts). Wrap them so clients
    see the same shape as typed exceptions.
    """
    exc = cast(StarletteHTTPException, exc)
    error_type = resolve_error_type(exc.status_code)

    detail = exc.detail
    content: dict[str, Any] = {"type": error_type}
    if isinstance(detail, dict):
        for key in _ALLOWED_DETAIL_KEYS:
            if key in detail:
                content[key] = detail[key]
        content.setdefault("message", "")
        content.setdefault("code", error_type.upper())
    else:
        content["message"] = str(detail) if detail is not None else ""
        content["code"] = error_type.upper()
    get_logger().info(
        "HTTP exception handled",
        path=request.url.path,
        status=exc.status_code,
    )
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler for unexpected errors.

    Logs with traceback and returns a generic 500 — never leaks the
    exception message to the client since it may contain stack traces
    or secrets.
    """
    get_logger().error(
        "Unhandled exception",
        path=request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "type": "api_error",
            "message": "An unexpected error occurred.",
            "code": "INTERNAL_ERROR",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register every global handler on the application instance.

    Call during app creation. Order matters only in that more-specific
    handlers should shadow more-generic ones; FastAPI dispatches by
    exception type, so registering both ``CoreException`` and
    ``Exception`` is safe.
    """
    app.add_exception_handler(CoreException, core_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


def _log_with_severity(logger: Any, exc: CoreException) -> None:
    """Route to a log level matching the exception severity.

    Keeps domain/use-case validation (often 4xx) out of error dashboards
    while still surfacing true infrastructure failures.
    """
    if exc.severity in (Severity.HIGH, Severity.CRITICAL):
        logger.error("Handled core exception", exc_info=exc)
    elif exc.severity is Severity.MEDIUM:
        logger.warning("Handled core exception", message=exc.message)
    else:
        logger.info("Handled core exception", message=exc.message)


__all__ = [
    "core_exception_handler",
    "http_exception_handler",
    "register_exception_handlers",
    "request_validation_exception_handler",
    "unhandled_exception_handler",
]
