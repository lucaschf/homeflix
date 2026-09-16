"""FastAPI routers for the settings BC."""

from src.modules.settings.presentation.routes.admin_settings_routes import (
    router as admin_settings_router,
)
from src.modules.settings.presentation.routes.settings_routes import (
    router as settings_router,
)

__all__ = ["admin_settings_router", "settings_router"]
