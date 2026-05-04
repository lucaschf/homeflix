"""Identity presentation routers."""

from src.modules.identity.presentation.routes.profile_routes import (
    router as profile_router,
)
from src.modules.identity.presentation.routes.users_routes import (
    router as users_router,
)

__all__ = ["profile_router", "users_router"]
