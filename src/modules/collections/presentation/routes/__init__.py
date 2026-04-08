"""Collections routes."""

from src.modules.collections.presentation.routes.custom_list_routes import (
    router as custom_list_router,
)
from src.modules.collections.presentation.routes.watchlist_routes import (
    router as watchlist_router,
)

__all__ = ["custom_list_router", "watchlist_router"]
