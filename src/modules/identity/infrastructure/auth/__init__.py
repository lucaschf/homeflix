"""FastAPI Users authentication wiring.

Lives in the infrastructure layer because it composes FastAPI dependency
chains (``Depends(...)``) rather than the dependency-injector style
used for our domain use cases. The two coexist: routes import
``current_active_user`` from here and use case factories from
``IdentityContainer``.
"""

from src.modules.identity.infrastructure.auth.backend import auth_backend
from src.modules.identity.infrastructure.auth.dependencies import get_session_token
from src.modules.identity.infrastructure.auth.fastapi_users import (
    current_active_user,
    current_admin_user,
    fastapi_users,
)

__all__ = [
    "auth_backend",
    "current_active_user",
    "current_admin_user",
    "fastapi_users",
    "get_session_token",
]
