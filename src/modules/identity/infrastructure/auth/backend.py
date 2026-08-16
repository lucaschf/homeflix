"""``AuthenticationBackend`` configuration: cookie transport + DB strategy.

Module-level singletons because FastAPI Users expects a stable
``auth_backend`` reference for ``fastapi_users.get_auth_router(...)``
and for ``fastapi_users.current_user(...)`` to compose. Configuration
values are read from ``Settings`` at import time via the cached
``get_settings()`` helper.
"""

from fastapi_users.authentication import AuthenticationBackend, CookieTransport

from src.config.settings import get_settings
from src.modules.identity.infrastructure.auth.dependencies import get_database_strategy


def _build_cookie_transport() -> CookieTransport:
    """Build the configured ``CookieTransport``.

    Hidden behind a function so tests / CLI scripts can call this
    after overriding settings; the module-level singleton below is
    what production uses.
    """
    settings = get_settings()
    return CookieTransport(
        cookie_name=settings.session_cookie_name,
        cookie_max_age=settings.session_lifetime_seconds,
        cookie_secure=settings.session_cookie_secure,
        cookie_httponly=True,
        cookie_samesite="strict",
    )


cookie_transport: CookieTransport = _build_cookie_transport()

auth_backend: AuthenticationBackend = AuthenticationBackend(  # type: ignore[type-arg]  # fastapi-users typing
    name="cookie-session",
    transport=cookie_transport,
    get_strategy=get_database_strategy,
)


__all__ = ["auth_backend", "cookie_transport"]
