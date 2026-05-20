"""Unit test fixtures for the notifications bounded context."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from src.modules.notifications.application.unit_of_work import (
    NotificationsUnitOfWork,
    NotificationsUnitOfWorkFactory,
)
from src.modules.notifications.domain.repositories import NotificationRepository


@dataclass
class NotificationsUoWMocks:
    """Bundle of mocks produced by ``make_notifications_uow_mock``."""

    factory: NotificationsUnitOfWorkFactory
    uow: NotificationsUnitOfWork
    notifications: AsyncMock


def make_notifications_uow_mock() -> NotificationsUoWMocks:
    """Build a mock :class:`NotificationsUnitOfWork` factory."""
    notifications = AsyncMock(spec=NotificationRepository)

    uow: NotificationsUnitOfWork = AsyncMock()
    uow.__aenter__.return_value = uow  # type: ignore[attr-defined]
    uow.__aexit__.return_value = None  # type: ignore[attr-defined]
    uow.notifications = notifications

    factory = MagicMock(return_value=uow)
    return NotificationsUoWMocks(
        factory=factory,
        uow=uow,
        notifications=notifications,
    )
