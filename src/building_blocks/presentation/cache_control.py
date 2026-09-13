"""Cache policy for JSON API responses.

API responses vary by the profile active in the session cookie: the
catalog, Continue Watching and the collections are filtered by that
profile's viewing policy (ADR-035), yet every profile requests the same
paths. The URL does not identify the response, so no shared cache and
no browser cache may reuse one across profiles. ``Vary: Cookie`` would
not help: a profile switch updates the session's ``access_tokens`` row
without re-emitting the cookie, so the request headers stay identical.

JSON responses that carry no ``Cache-Control`` of their own therefore
get ``Cache-Control: no-store``. That covers the error envelopes built
by the global exception handlers — a ``403 CONTENT_RESTRICTED_*`` is as
profile-specific as a ``200`` — because Starlette turns exceptions into
those responses inside every user middleware: at route level for
anything raised by an endpoint or its dependencies (the session guard
included), and in ``ExceptionMiddleware`` for routing errors (404 on an
unmatched path, 405). The catch-all ``Exception`` handler is the
exception: Starlette mounts it in ``ServerErrorMiddleware``, outside, so
a generic 500 goes out without the header; it carries no profile data.

Everything else passes through untouched: a response that already sets
``Cache-Control`` made its own decision, and non-JSON responses —
mirrored artwork, HLS playlists and segments, VTT, CORS preflights —
keep the caching the player and ``<img>`` tags rely on.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_CACHE_CONTROL_HEADER = "Cache-Control"
_NO_STORE = "no-store"
_JSON_MEDIA_TYPE = "application/json"
_JSON_STRUCTURED_SUFFIX = "+json"


def _is_json(content_type: str | None) -> bool:
    """Tell whether a ``Content-Type`` header value names a JSON media type.

    Args:
        content_type: Raw header value, parameters included
            (e.g. ``application/json; charset=utf-8``), or ``None``.

    Returns:
        ``True`` for ``application/json`` and any ``+json`` structured
        syntax suffix (e.g. ``application/problem+json``).
    """
    if not content_type:
        return False
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type == _JSON_MEDIA_TYPE or media_type.endswith(_JSON_STRUCTURED_SUFFIX)


class JsonNoStoreMiddleware(BaseHTTPMiddleware):
    """Mark JSON responses without their own ``Cache-Control`` as ``no-store``.

    Only headers are touched; the body is never read, so streamed
    responses keep streaming.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Add ``Cache-Control: no-store`` to an uncached JSON response."""
        response = await call_next(request)
        if _CACHE_CONTROL_HEADER not in response.headers and _is_json(
            response.headers.get("content-type")
        ):
            response.headers[_CACHE_CONTROL_HEADER] = _NO_STORE
        return response


__all__ = ["JsonNoStoreMiddleware"]
