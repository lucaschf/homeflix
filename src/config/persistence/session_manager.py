"""Per-request session lifecycle management.

Tracks AsyncSession instances created during a request and ensures
they are closed when the request finishes, preventing connection leaks.
"""

from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_request_sessions: ContextVar[list[AsyncSession]] = ContextVar(
    "_request_sessions",
    default=[],
)


def create_tracked_session(factory: async_sessionmaker[AsyncSession]) -> AsyncSession:
    """Create a session and register it for cleanup at request end.

    Args:
        factory: The async_sessionmaker to create the session from.

    Returns:
        A new AsyncSession that will be closed automatically.
    """
    session = factory()
    try:
        sessions = _request_sessions.get()
    except LookupError:
        # No request context (e.g. startup code) — session is untracked
        return session
    sessions.append(session)
    return session


class SessionCleanupMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    """Middleware that closes all tracked sessions after each request."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Run the request and close tracked sessions afterwards."""
        sessions: list[AsyncSession] = []
        token = _request_sessions.set(sessions)
        try:
            response = await call_next(request)
            return response
        finally:
            for session in sessions:
                await session.close()
            _request_sessions.reset(token)
