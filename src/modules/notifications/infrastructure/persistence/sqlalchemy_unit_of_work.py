"""SQLAlchemy implementation of ``NotificationsUnitOfWork``."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.modules.notifications.application.unit_of_work import (
    NotificationsUnitOfWork,
    NotificationsUnitOfWorkFactory,
)
from src.modules.notifications.infrastructure.persistence.repositories import (
    SQLAlchemyNotificationRepository,
)


class SqlAlchemyNotificationsUnitOfWork(SqlAlchemyUnitOfWork, NotificationsUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the notifications BC."""

    def _build_repositories(self, session: AsyncSession) -> None:
        self.notifications = SQLAlchemyNotificationRepository(session)


class SqlAlchemyNotificationsUnitOfWorkFactory(NotificationsUnitOfWorkFactory):
    """Produce fresh ``SqlAlchemyNotificationsUnitOfWork`` instances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> NotificationsUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""
        return SqlAlchemyNotificationsUnitOfWork(self._session_factory)


__all__ = [
    "SqlAlchemyNotificationsUnitOfWork",
    "SqlAlchemyNotificationsUnitOfWorkFactory",
]
