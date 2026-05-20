"""Notifications bounded-context Unit of Work interface."""

from abc import ABC, abstractmethod

from src.building_blocks.application.unit_of_work import UnitOfWork
from src.modules.notifications.domain.repositories import NotificationRepository


class NotificationsUnitOfWork(UnitOfWork):
    """Transactional boundary for notification writes."""

    notifications: NotificationRepository


class NotificationsUnitOfWorkFactory(ABC):
    """Builds fresh ``NotificationsUnitOfWork`` instances on demand."""

    @abstractmethod
    def __call__(self) -> NotificationsUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""


__all__ = ["NotificationsUnitOfWork", "NotificationsUnitOfWorkFactory"]
