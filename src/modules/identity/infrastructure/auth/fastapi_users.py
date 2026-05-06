"""``FastAPIUsers`` singleton plus the auth dependencies.

Routes import ``current_active_user`` (or ``current_admin_user``) from
this module (or from the package
``src.modules.identity.infrastructure.auth``) and use it as
``Depends(...)`` to gate a route. ``current_admin_user`` layers a role
check on top of ``current_active_user`` so write-side endpoints
(library CRUD, scan, enrichment, intro markers, file management) stay
restricted to operators of the household, while regular members can
still hit read endpoints, watch progress, collections and profile
management.
"""

import uuid

from fastapi import Depends
from fastapi_users import FastAPIUsers

from src.building_blocks.application.errors import ForbiddenOperationException
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.auth.backend import auth_backend
from src.modules.identity.infrastructure.auth.dependencies import get_user_manager
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel

fastapi_users: FastAPIUsers[UserModel, uuid.UUID] = FastAPIUsers[UserModel, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)


async def current_admin_user(
    user: UserModel = Depends(current_active_user),
) -> UserModel:
    """Require the authenticated user to carry the ``admin`` role.

    Composes on top of ``current_active_user`` — the underlying chain
    still validates the cookie + active flag — and adds a role check
    so write-side household-management endpoints (library CRUD, scan,
    enrichment, intro markers, file management, HLS cache flush) are
    only reachable by the household operator.

    Raises:
        ForbiddenOperationException: When the authenticated user's
            role is not ``admin``. The application exception handler
            translates this into HTTP 403 with the standard error
            envelope.
    """
    if user.role != UserRole.ADMIN.value:
        raise ForbiddenOperationException(
            message="Admin role required",
            message_code="ADMIN_REQUIRED",
            required_permission="admin",
        )
    return user


__all__ = ["current_active_user", "current_admin_user", "fastapi_users"]
