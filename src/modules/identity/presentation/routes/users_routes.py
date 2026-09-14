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
from src.modules.identity.application.dtos.identity_dtos import GetAdminAccessInput
from src.modules.identity.application.use_cases.get_active_profile_for_session import (
    GetActiveProfileForSessionUseCase,
)
from src.modules.identity.application.use_cases.get_admin_access import GetAdminAccessUseCase
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.auth import (
    current_active_user,
    get_session_token,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.presentation.schemas.user_schemas import UserRead

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get("/me")
@inject
async def get_me(
    user: UserModel = Depends(current_active_user),
    session_token: str = Depends(get_session_token),
    get_active_profile: GetActiveProfileForSessionUseCase = Depends(
        Provide[ApplicationContainer.identity.get_active_profile_for_session],
    ),
    get_admin_access: GetAdminAccessUseCase = Depends(
        Provide[ApplicationContainer.identity.get_admin_access],
    ),
) -> dict[str, Any]:
    """Return the authenticated user plus the session's active profile.

    ``active_profile_id`` is the prefixed external id (``prf_xxx``)
    of the profile currently bound to this session, sourced from
    ``access_tokens.current_profile_id``. ``None`` until the user
    selects a profile via ``POST /profiles/{id}/switch``.

    ``admin_access`` is the admin read authority of this session:
    ``none``, ``granted`` or ``suspended`` (ADR-035, Amendment 7).
    """
    active_profile_id = await get_active_profile.execute(session_token)
    admin_access = await get_admin_access.execute(
        GetAdminAccessInput(
            user_id=user.external_id,
            role=UserRole(user.role),
            parental_pin_configured=user.parental_pin_hash is not None,
            session_token=session_token,
        ),
    )
    return api_single(
        "user",
        UserRead.from_model(
            user,
            active_profile_id=active_profile_id,
            admin_access=admin_access,
        ).model_dump(),
    )


__all__ = ["router"]
