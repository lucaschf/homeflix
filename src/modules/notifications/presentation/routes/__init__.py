"""Notifications REST routes."""

from src.modules.notifications.presentation.routes.notification_routes import (
    router as notification_router,
)

__all__ = ["notification_router"]
