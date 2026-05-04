"""FastAPI dependency that resolves the caller's ``profile_id`` for collections.

Same per-profile rollout pattern documented in
``watch_progress/presentation/dependencies.py``: try the
authenticated path first, fall back to
``settings.collections_default_profile_id`` when no cookie is
present, raise 401 otherwise. Once strict mode is acceptable
project-wide, this dep can be replaced by a direct re-export of
``identity.presentation.dependencies.get_current_profile``.
"""

from fastapi import Request

from src.config.settings import get_settings
from src.modules.identity.domain.errors import NoActiveSessionError


async def resolve_profile_id(request: Request) -> str:
    """Return the caller's profile_id (prefixed external ID).

    Errors raised by the identity UoW (container not wired, DB
    unreachable, etc.) propagate as 500 by design — silently falling
    back to anonymous on real misconfigurations would mask bugs and
    serve authenticated requests as anonymous.
    """
    settings = get_settings()

    token = request.cookies.get(settings.session_cookie_name)
    if token is not None:
        container = request.app.state.container
        factory = container.identity.identity_unit_of_work_factory()
        async with factory() as uow:
            snap = await uow.access_tokens.get_by_token(token)
        if snap is not None and snap.current_profile_id is not None:
            return str(snap.current_profile_id)

    if settings.collections_default_profile_id:
        return settings.collections_default_profile_id

    raise NoActiveSessionError(message="Authentication required to access collections")


__all__ = ["resolve_profile_id"]
