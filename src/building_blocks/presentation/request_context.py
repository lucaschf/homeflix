"""Per-request context middleware.

Attaches a correlation id to every request:

- Reads ``X-Request-ID`` from the incoming request, or generates one.
- Exposes it via a ``ContextVar`` so application and infrastructure
  code (e.g. error handlers, logging) can reach the current request id
  without threading it through every function.
- Echoes the id back on the response as ``X-Request-ID`` and emits a
  coarse ``Server-Timing`` header so operators can see per-request
  latency without parsing the payload.
"""

import time
import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_HEADER = "X-Request-ID"
_current_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_current_request_id() -> str | None:
    """Return the current request id, if a request is in flight.

    Returns:
        The id attached to the current request, or ``None`` outside a
        request (e.g. scheduled jobs).
    """
    return _current_request_id.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Set request id, log context, and timing headers for each request.

    The middleware must run before route handlers so error handlers and
    loggers see the bound request id even when the handler raises.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Wrap the request with correlation id and timing."""
        incoming = request.headers.get(_REQUEST_ID_HEADER)
        request_id = incoming or f"req_{uuid.uuid4().hex[:16]}"

        token = _current_request_id.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            _current_request_id.reset(token)
            structlog.contextvars.unbind_contextvars("request_id")

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[_REQUEST_ID_HEADER] = request_id
        response.headers["Server-Timing"] = f"total;dur={duration_ms:.0f}"
        return response


__all__ = [
    "RequestContextMiddleware",
    "get_current_request_id",
]
