"""Admin REST API routes for user management.

Surface for the ``/admin/users`` panel: list / detail / create /
role-flip / soft-delete. Profile management for *other* users is
deliberately read-only here (P3 scope); members keep editing their
own profiles via the user-facing ``/api/v1/profiles`` endpoints.
"""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.application.dtos import (
    CreateAdminUserInput,
    DeleteAdminUserInput,
    GetUserDetailInput,
    ListUsersInput,
    UpdateUserRoleInput,
)
from src.modules.identity.application.use_cases.create_admin_user import (
    CreateAdminUserUseCase,
)
from src.modules.identity.application.use_cases.delete_admin_user import (
    DeleteAdminUserUseCase,
)
from src.modules.identity.application.use_cases.get_user_detail import (
    GetUserDetailUseCase,
)
from src.modules.identity.application.use_cases.list_users import ListUsersUseCase
from src.modules.identity.application.use_cases.update_user_role import (
    UpdateUserRoleUseCase,
)
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.auth import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.presentation.schemas import (
    CreateAdminUserRequest,
    UpdateUserRoleRequest,
)

router = APIRouter(prefix="/api/v1/admin/users", tags=["Admin — Users"])


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_admin_users(
    role: UserRole | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: UserModel = Depends(current_admin_user),
    use_case: ListUsersUseCase = Depends(
        Provide[ApplicationContainer.identity.list_users],
    ),
) -> dict[str, Any]:
    """Page through users, optionally filtered by role.

    Each row carries the profile count so the admin can eyeball
    multi-profile households without opening detail.
    """
    summaries = await use_case.execute(
        ListUsersInput(role=role, limit=limit, offset=offset),
    )
    return api_list([asdict(s) for s in summaries])


@router.post("", status_code=201)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def create_admin_user(
    body: CreateAdminUserRequest,
    _admin: UserModel = Depends(current_admin_user),
    use_case: CreateAdminUserUseCase = Depends(
        Provide[ApplicationContainer.identity.create_admin_user],
    ),
) -> dict[str, Any]:
    """Create a fresh user with the provided email, password and role.

    The user is created as ``is_verified=True`` so they can log in
    immediately; they're expected to change the initial password
    from the user-facing ``/settings`` after first sign-in.
    """
    summary = await use_case.execute(
        CreateAdminUserInput(
            email=body.email,
            password=body.password,
            role=body.role,
        ),
    )
    return api_single("user", asdict(summary))


@router.get("/{user_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_admin_user(
    user_id: str,
    _admin: UserModel = Depends(current_admin_user),
    use_case: GetUserDetailUseCase = Depends(
        Provide[ApplicationContainer.identity.get_user_detail],
    ),
) -> dict[str, Any]:
    """Return the user + their (read-only) profile list."""
    detail = await use_case.execute(GetUserDetailInput(user_id=user_id))
    return api_single("user", asdict(detail))


@router.patch("/{user_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def update_admin_user_role(
    user_id: str,
    body: UpdateUserRoleRequest,
    admin: UserModel = Depends(current_admin_user),
    use_case: UpdateUserRoleUseCase = Depends(
        Provide[ApplicationContainer.identity.update_user_role],
    ),
) -> dict[str, Any]:
    """Flip the user's role; refuses to demote the last active admin."""
    summary = await use_case.execute(
        UpdateUserRoleInput(
            user_id=user_id,
            role=body.role,
            acting_admin_id=admin.external_id,
        ),
    )
    return api_single("user", asdict(summary))


@router.delete("/{user_id}", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def delete_admin_user(
    user_id: str,
    admin: UserModel = Depends(current_admin_user),
    use_case: DeleteAdminUserUseCase = Depends(
        Provide[ApplicationContainer.identity.delete_admin_user],
    ),
) -> None:
    """Soft-delete a user and fan out the cross-BC cleanup cascade.

    Refuses with HTTP 409 when the call would delete the caller's
    own account or the last active admin.
    """
    await use_case.execute(
        DeleteAdminUserInput(user_id=user_id, acting_admin_id=admin.external_id),
    )


__all__ = ["router"]
