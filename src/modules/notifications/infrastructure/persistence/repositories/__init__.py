"""Notifications repository implementations."""

from src.modules.notifications.infrastructure.persistence.repositories.notification_repository import (
    SQLAlchemyNotificationRepository,
)

__all__ = ["SQLAlchemyNotificationRepository"]
