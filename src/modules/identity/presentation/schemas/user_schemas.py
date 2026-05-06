"""Pydantic schemas for the identity user endpoints.

We intentionally do NOT use ``fastapi_users.schemas.BaseUser[UUID]``
because it serializes the database UUID as ``id`` — that contradicts
ADR-002, which mandates prefixed external IDs at every API surface.
``UserRead`` here exposes ``id`` as the prefixed ``external_id`` and
hides the UUID entirely.
"""

from typing import Self

from pydantic import BaseModel

from src.modules.identity.infrastructure.persistence.models.user_model import UserModel


class UserRead(BaseModel):
    """Public read shape for the authenticated user (``GET /users/me``).

    ``active_profile_id`` mirrors ``access_tokens.current_profile_id``
    for the caller's session so the frontend can render
    profile-scoped UI (the navbar avatar chip, the active-profile
    badge) without keeping a localStorage shadow of the value. It is
    ``None`` while the session has not yet selected a profile
    (post-login, pre-picker), and switches to a prefixed ``prf_xxx``
    once the user hits ``POST /profiles/{id}/switch``.
    """

    id: str
    email: str
    role: str
    is_active: bool
    is_verified: bool
    active_profile_id: str | None = None

    @classmethod
    def from_model(cls, user: UserModel, active_profile_id: str | None = None) -> Self:
        """Project a ``UserModel`` into the API response shape.

        Only the prefixed ``external_id`` is exposed as ``id`` — the
        database UUID never leaves infrastructure. ``active_profile_id``
        is supplied by the route after a session-token lookup; the
        schema itself stays decoupled from access-token storage.
        """
        return cls(
            id=user.external_id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            active_profile_id=active_profile_id,
        )


__all__ = ["UserRead"]
