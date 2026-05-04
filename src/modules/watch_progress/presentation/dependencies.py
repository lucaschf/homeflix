"""FastAPI dependencies that resolve the caller's ``profile_id``.

During the per-profile rollout (see ADR-010), watch_progress routes
need a way to scope data by profile *before* every consumer is sending
the session cookie. ``resolve_profile_id`` implements the transition
strategy: try the authenticated path first, fall back to the
configured ``watch_progress_default_profile_id`` setting when no
cookie is present, and finally raise ``NoActiveSessionError`` (HTTP
401) if neither works.

Once every consumer ships login support, unset the
``WATCH_PROGRESS_DEFAULT_PROFILE_ID`` env var so the dependency runs
strictly — at that point we can also collapse this dep into a direct
re-export of ``identity.presentation.dependencies.get_current_profile``.
"""

from contextlib import suppress

from fastapi import Request

from src.config.settings import get_settings
from src.modules.identity.domain.errors import NoActiveSessionError


async def resolve_profile_id(request: Request) -> str:
    """Return the caller's profile_id (prefixed external ID).

    Resolution order:

    1. Session cookie present → look up the matching access_tokens row
       in the identity BC's UoW. If a ``current_profile_id`` exists,
       return it.
    2. No usable cookie + ``watch_progress_default_profile_id`` setting
       configured → return that fallback (transition mode).
    3. Otherwise → raise :class:`NoActiveSessionError` (HTTP 401).
    """
    settings = get_settings()

    token = request.cookies.get(settings.session_cookie_name)
    if token is not None:
        with suppress(Exception):
            container = request.app.state.container
            factory = container.identity.identity_unit_of_work_factory()
            async with factory() as uow:
                snap = await uow.access_tokens.get_by_token(token)
            if snap is not None and snap.current_profile_id is not None:
                return str(snap.current_profile_id)

    if settings.watch_progress_default_profile_id:
        return settings.watch_progress_default_profile_id

    raise NoActiveSessionError(message="Authentication required to access watch progress")


__all__ = ["resolve_profile_id"]
