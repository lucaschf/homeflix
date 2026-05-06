"""Custom user routes for the identity bounded context.

The full FastAPI Users users-router (``fastapi_users.get_users_router``)
exposes ``/me`` and admin CRUD with the database UUID as ``id`` —
which contradicts ADR-002. We mount only what we need here, with the
prefixed ``external_id`` returned as ``id``.
"""

from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.application.use_cases.get_active_profile_for_session import (
    GetActiveProfileForSessionUseCase,
)
from src.modules.identity.infrastructure.auth import (
    current_active_user,
    get_session_token,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.presentation.schemas.user_schemas import UserRead

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get("/me")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_me(
    user: UserModel = Depends(current_active_user),
    session_token: str = Depends(get_session_token),
    get_active_profile: GetActiveProfileForSessionUseCase = Depends(
        Provide[ApplicationContainer.identity.get_active_profile_for_session],
    ),
) -> dict[str, Any]:
    """Return the authenticated user plus the session's active profile.

    ``active_profile_id`` is the prefixed external id (``prf_xxx``)
    of the profile currently bound to this session, sourced from
    ``access_tokens.current_profile_id``. ``None`` until the user
    selects a profile via ``POST /profiles/{id}/switch``.
    """
    active_profile_id = await get_active_profile.execute(session_token)
    return api_single(
        "user",
        UserRead.from_model(user, active_profile_id=active_profile_id).model_dump(),
    )


__all__ = ["router"]
