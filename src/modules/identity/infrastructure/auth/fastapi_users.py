"""``FastAPIUsers`` singleton and the ``current_active_user`` dependency.

Routes import ``current_active_user`` from this module (or from the
package ``src.modules.identity.infrastructure.auth``) and use it as
``Depends(current_active_user)`` to require an authenticated, active
user on a route.
"""

import uuid

from fastapi_users import FastAPIUsers

from src.modules.identity.infrastructure.auth.backend import auth_backend
from src.modules.identity.infrastructure.auth.dependencies import get_user_manager
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel

fastapi_users: FastAPIUsers[UserModel, uuid.UUID] = FastAPIUsers[UserModel, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)

__all__ = ["current_active_user", "fastapi_users"]
