"""Identity presentation routers."""

from src.modules.identity.presentation.routes.admin_user_routes import (
    router as admin_user_router,
)
from src.modules.identity.presentation.routes.parental_routes import (
    router as parental_router,
)
from src.modules.identity.presentation.routes.profile_routes import (
    router as profile_router,
)
from src.modules.identity.presentation.routes.users_routes import (
    router as users_router,
)

__all__ = ["admin_user_router", "parental_router", "profile_router", "users_router"]
