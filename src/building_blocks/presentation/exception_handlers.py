"""Global exception-to-HTTP translation.

Centralises how domain, application, and infrastructure exceptions
surface to API clients. Routes raise typed exceptions; these handlers
translate them into the v3.0 error envelope without every controller
repeating the mapping.

Handlers are intentionally narrow — each knows only how to log and
serialize a category of errors. The envelope format comes from
``CoreException.to_dict()`` so the contract stays in one place.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from src.building_blocks.domain.errors import CoreException, Severity
from src.config.logging import get_logger

_STATUS_TO_ERROR_TYPE = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    405: "invalid_request_error",
    409: "conflict_error",
    413: "request_too_large_error",
    415: "invalid_request_error",
    422: "validation_error",
    429: "rate_limit_error",
    500: "api_error",
    502: "bad_gateway_error",
    503: "service_unavailable_error",
    504: "gateway_timeout_error",
}


async def core_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate typed domain/application/infra exceptions into HTTP.

    Logging level is chosen from ``exc.severity`` so a 4xx doesn't look
    like a 5xx in the logs. The payload uses ``CoreException.to_dict()``
    — no sensitive ``_internal`` block is ever serialized.
    """
    assert isinstance(exc, CoreException)  # narrow type for handler signature
    logger = get_logger().bind(
        exception_id=exc.exception_id,
        code=exc.code,
        http_status=exc.http_status,
        path=request.url.path,
    )
    _log_with_severity(logger, exc)

    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


async def request_validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Format FastAPI/Pydantic request validation errors in v3 shape."""
    assert isinstance(exc, RequestValidationError)
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
    assert isinstance(exc, StarletteHTTPException)
    error_type = _STATUS_TO_ERROR_TYPE.get(exc.status_code, "api_error")

    detail = exc.detail
    if isinstance(detail, dict):
        content: dict[str, Any] = {"type": error_type, **detail}
    else:
        content = {
            "type": error_type,
            "message": str(detail) if detail is not None else "",
            "code": error_type.upper(),
        }
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
