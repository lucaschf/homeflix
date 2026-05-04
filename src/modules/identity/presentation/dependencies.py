"""FastAPI dependencies that resolve the caller's identity context.

Two layers:

1. ``get_current_profile`` — the strict-mode dep. Combines the
   authenticated ``UserModel`` from FastAPI Users with the active
   ``profile_id`` carried by the session row, returning a
   ``ProfileContext`` with both as prefixed external IDs (UUIDs
   never cross into the domain).
2. ``make_resolve_profile_id`` — the transitional factory. Returns
   a per-BC dep that tries the cookie path first and falls back to
   a configured ``*_default_profile_id`` setting when the request
   has no session yet. Each consumer BC (``watch_progress``,
   ``collections``, ``preferences``, ``media``) wires its own
   bound dep at module level, parameterising the setting attribute
   and the missing-session error message. Once every consumer
   ships login support and the env vars are unset, the helpers
   collapse into a direct re-export of ``get_current_profile``.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends, Request

from src.config.settings import get_settings
from src.modules.identity.domain.errors import (
    NoActiveProfileSelectedError,
    NoActiveSessionError,
)
from src.modules.identity.infrastructure.auth import (
    current_active_user,
    get_session_token,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


@dataclass(frozen=True)
class ProfileContext:
    """Per-request identity context.

    Carries everything a use case needs to act on behalf of the
    caller: the authenticated user, the active personalization
    profile, and the opaque session token (so the switch-profile use
    case can update the same session row that is currently being
    served).
    """

    user_id: UserId
    profile_id: ProfileId
    session_token: str


async def get_current_profile(
    request: Request,
    user: UserModel = Depends(current_active_user),
    token: str = Depends(get_session_token),
) -> ProfileContext:
    """Resolve the active ``ProfileContext`` for the request.

    Steps:

    1. ``Depends(current_active_user)`` already authenticated the
       cookie and produced the ``UserModel``. If the cookie was
       missing or invalid the dependency raised before reaching this
       function.
    2. ``Depends(get_session_token)`` recovers the opaque token from
       the cookie (single source of truth for cookie name + missing
       cookie → 401 mapping).
    3. Look up the matching ``access_tokens`` row to find the
       ``current_profile_id`` chosen for this session.
    4. Raise :class:`NoActiveProfileSelectedError` (HTTP 409) if the
       user has not yet selected a profile, so the frontend can
       distinguish "logged in, pick a profile" from "not logged in".
    """
    container = request.app.state.container
    factory = container.identity.identity_unit_of_work_factory()
    async with factory() as uow:
        snapshot = await uow.access_tokens.get_by_token(token)

    if snapshot is None:
        raise NoActiveSessionError(message="Session token is unknown")

    if snapshot.current_profile_id is None:
        raise NoActiveProfileSelectedError(
            message="Select a profile before continuing",
        )

    return ProfileContext(
        user_id=UserId(user.external_id),
        profile_id=snapshot.current_profile_id,
        session_token=token,
    )


def make_resolve_profile_id(
    *,
    setting_attr: str,
    missing_message: str,
) -> Callable[[Request], Awaitable[str]]:
    """Build a per-BC ``resolve_profile_id`` dep with a transitional fallback.

    Resolution order at request time:

    1. Session cookie present → look up the matching ``access_tokens``
       row in the identity BC's UoW. If a ``current_profile_id``
       exists, return it.
    2. No usable cookie or unknown token + the configured
       ``settings.<setting_attr>`` is set → return that fallback
       (transition mode).
    3. Otherwise → raise :class:`NoActiveSessionError` (HTTP 401)
       with ``missing_message``.

    Errors raised by the identity UoW (container not wired, DB
    unreachable, etc.) propagate as 500 by design — silently falling
    back to anonymous on real misconfigurations would mask bugs and
    serve authenticated requests as anonymous.

    Args:
        setting_attr: Name of the field on ``Settings`` that holds
            the per-BC fallback (e.g. ``"watch_progress_default_profile_id"``).
            ``getattr`` is read every request so changes to the
            setting (when sourced from a re-loaded ``.env``) take
            effect without restarting.
        missing_message: User-facing 401 message when neither path
            resolves a profile.

    Returns:
        An ``async`` FastAPI dep returning the prefixed profile_id
        as a plain ``str`` — kept primitive because every consumer
        passes it straight into a use case input that already
        validates the prefix.
    """

    async def resolve_profile_id(request: Request) -> str:
        settings = get_settings()

        token = request.cookies.get(settings.session_cookie_name)
        if token is not None:
            container = request.app.state.container
            factory = container.identity.identity_unit_of_work_factory()
            async with factory() as uow:
                snap = await uow.access_tokens.get_by_token(token)
            if snap is not None and snap.current_profile_id is not None:
                return str(snap.current_profile_id)

        fallback = getattr(settings, setting_attr)
        if fallback:
            return str(fallback)

        raise NoActiveSessionError(message=missing_message)

    return resolve_profile_id


__all__ = ["ProfileContext", "get_current_profile", "make_resolve_profile_id"]
