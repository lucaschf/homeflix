"""FastAPI dependencies that resolve the caller's identity context.

The single entry point is ``get_current_profile``: it combines the
authenticated ``UserModel`` from FastAPI Users with the active
``profile_id`` carried by the session row, returning a
``ProfileContext`` with both as prefixed external IDs (UUIDs never
cross into the domain).

Shipped in PR 1 deliberately unused — the consumer BCs
(``watch_progress``, ``collections``, ``preferences``) pick this up
in subsequent PRs to enforce per-profile isolation. Adding it now
means PR 2 can import the dependency on day one without waiting on
any further wiring.
"""

from dataclasses import dataclass

from fastapi import Depends, Request

from src.modules.identity.domain.errors import (
    NoActiveProfileSelectedError,
    NoActiveSessionError,
)
from src.modules.identity.domain.value_objects.profile_id import ProfileId
from src.modules.identity.domain.value_objects.user_id import UserId
from src.modules.identity.infrastructure.auth import (
    current_active_user,
    get_session_token,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel


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


__all__ = ["ProfileContext", "get_current_profile"]
