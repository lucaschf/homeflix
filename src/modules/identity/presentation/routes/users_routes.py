"""Custom user routes for the identity bounded context.

The full FastAPI Users users-router (``fastapi_users.get_users_router``)
exposes ``/me`` and admin CRUD with the database UUID as ``id`` —
which contradicts ADR-002. We mount only what we need here, with the
prefixed ``external_id`` returned as ``id``.
"""

from typing import Any

from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_single
from src.modules.identity.infrastructure.auth import current_active_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.presentation.schemas.user_schemas import UserRead

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get("/me")  # type: ignore[misc]
async def get_me(
    user: UserModel = Depends(current_active_user),
) -> dict[str, Any]:
    """Return the authenticated user with prefixed external IDs."""
    return api_single("user", UserRead.from_model(user).model_dump())


__all__ = ["router"]
