"""SQLAlchemy implementation of WatchProgressUnitOfWork."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWork,
    WatchProgressUnitOfWorkFactory,
)
from src.modules.watch_progress.infrastructure.persistence.repositories.watch_progress_repository import (
    SQLAlchemyWatchProgressRepository,
)


class SqlAlchemyWatchProgressUnitOfWork(SqlAlchemyUnitOfWork, WatchProgressUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the watch_progress context."""

    def _build_repositories(self, session: AsyncSession) -> None:
        self.progress = SQLAlchemyWatchProgressRepository(session)


class SqlAlchemyWatchProgressUnitOfWorkFactory(WatchProgressUnitOfWorkFactory):
    """Produce fresh :class:`SqlAlchemyWatchProgressUnitOfWork` instances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> WatchProgressUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""
        return SqlAlchemyWatchProgressUnitOfWork(self._session_factory)


__all__ = [
    "SqlAlchemyWatchProgressUnitOfWork",
    "SqlAlchemyWatchProgressUnitOfWorkFactory",
]
