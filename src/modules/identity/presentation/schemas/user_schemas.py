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
    """Public read shape for the authenticated user (``GET /users/me``)."""

    id: str
    email: str
    role: str
    is_active: bool
    is_verified: bool

    @classmethod
    def from_model(cls, user: UserModel) -> Self:
        """Project a ``UserModel`` into the API response shape.

        Only the prefixed ``external_id`` is exposed as ``id`` — the
        database UUID never leaves infrastructure.
        """
        return cls(
            id=user.external_id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
        )


__all__ = ["UserRead"]
