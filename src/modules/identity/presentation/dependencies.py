"""FastAPI dependencies that resolve the caller's identity context.

Two layers, both strict (no transitional fallback):

1. ``get_current_profile`` — combines the authenticated ``UserModel``
   from FastAPI Users with the active ``profile_id`` carried by the
   session row, returning a ``ProfileContext`` with both as
   prefixed external IDs (UUIDs never cross into the domain).
2. ``resolve_profile_id`` — the lighter dep used by the per-BC
   catalog reads (watch_progress, collections, preferences, media).
   Reads the session cookie, looks up the matching ``access_tokens``
   row and returns ``current_profile_id``. Raises 401 when the
   cookie is missing or the row has no profile selected.

The earlier ``make_resolve_profile_id`` factory threaded a per-BC
``*_default_profile_id`` env-var fallback through this path so the
old frontend (pre-login) could keep serving anonymous catalog
requests during the rollout (PRs #163-180). With the route guards
in ``homeflix-web`` (#107-#112) anonymous requests never reach the
catalog, so the fallback was dead code in practice. Removed in this
cleanup so the entry point is a single function with one
behaviour — easier to reason about and to migrate when the next
auth feature lands.
"""

import inspect
from dataclasses import dataclass

from fastapi import Depends, Request

from src.config.settings import get_settings
from src.modules.identity.application.errors import (
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


async def _resolve_uow_factory(request: Request):  # type: ignore[no-untyped-def]
    """Resolve the identity UoW factory from ``app.state.container``.

    ``infrastructure.session_factory`` is a ``providers.Resource`` in
    production: invoking the wrapping ``identity_unit_of_work_factory``
    provider returns a Future. Tests override the session factory with
    ``providers.Object``, which returns synchronously. The
    ``isawaitable`` branch covers both shapes.
    """
    factory = request.app.state.container.identity.identity_unit_of_work_factory()
    if inspect.isawaitable(factory):
        factory = await factory
    return factory


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
    factory = await _resolve_uow_factory(request)
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


async def resolve_profile_id(request: Request) -> str:
    """Return the caller's prefixed ``profile_id`` (``prf_xxx``).

    Resolution:

    1. Session cookie missing → :class:`NoActiveSessionError` (HTTP 401).
    2. Cookie present but the matching ``access_tokens`` row has no
       ``current_profile_id`` (logged in, picker not visited yet) →
       same 401.
    3. Otherwise → return the ``current_profile_id`` as a plain
       string.

    Errors raised by the identity UoW (container not wired, DB
    unreachable, etc.) propagate as 500 by design — silently
    degrading to anonymous on real misconfigurations would mask
    bugs and serve authenticated requests as anonymous data.
    """
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token is None:
        raise NoActiveSessionError(message="Authentication required")

    factory = await _resolve_uow_factory(request)
    async with factory() as uow:
        snap = await uow.access_tokens.get_by_token(token)

    if snap is None or snap.current_profile_id is None:
        raise NoActiveSessionError(message="Authentication required")

    return str(snap.current_profile_id)


__all__ = ["ProfileContext", "get_current_profile", "resolve_profile_id"]
