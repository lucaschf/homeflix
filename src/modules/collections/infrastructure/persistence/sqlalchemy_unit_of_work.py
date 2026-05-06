"""SQLAlchemy implementation of CollectionsUnitOfWork."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.modules.collections.application.unit_of_work import (
    CollectionsUnitOfWork,
    CollectionsUnitOfWorkFactory,
)
from src.modules.collections.infrastructure.persistence.repositories.custom_list_repository import (
    SQLAlchemyCustomListRepository,
)
from src.modules.collections.infrastructure.persistence.repositories.watchlist_repository import (
    SQLAlchemyWatchlistRepository,
)


class SqlAlchemyCollectionsUnitOfWork(SqlAlchemyUnitOfWork, CollectionsUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the collections bounded context."""

    def _build_repositories(self, session: AsyncSession) -> None:
        self.watchlist = SQLAlchemyWatchlistRepository(session)
        self.custom_lists = SQLAlchemyCustomListRepository(session)


class SqlAlchemyCollectionsUnitOfWorkFactory(CollectionsUnitOfWorkFactory):
    """Produce fresh :class:`SqlAlchemyCollectionsUnitOfWork` instances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> CollectionsUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""
        return SqlAlchemyCollectionsUnitOfWork(self._session_factory)


__all__ = [
    "SqlAlchemyCollectionsUnitOfWork",
    "SqlAlchemyCollectionsUnitOfWorkFactory",
]
