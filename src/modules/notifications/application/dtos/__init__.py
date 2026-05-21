"""Notifications application DTOs."""

from src.modules.notifications.application.dtos.notification_dtos import (
    CreateNotificationInput,
    ListUserNotificationsInput,
    MarkAllNotificationsReadInput,
    MarkAllNotificationsReadOutput,
    MarkNotificationReadInput,
    NotificationOutput,
)

__all__ = [
    "CreateNotificationInput",
    "ListUserNotificationsInput",
    "MarkAllNotificationsReadInput",
    "MarkAllNotificationsReadOutput",
    "MarkNotificationReadInput",
    "NotificationOutput",
]
