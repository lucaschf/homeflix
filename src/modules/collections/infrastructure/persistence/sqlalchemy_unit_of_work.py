"""SQLAlchemy implementation of CollectionsUnitOfWork."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.persistence.session_manager import create_tracked_session
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


class SqlAlchemyCollectionsUnitOfWork(CollectionsUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the collections bounded context."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError(
                "CollectionsUnitOfWork is already active; nested use is not supported."
            )
        self._session = create_tracked_session(self._session_factory)
        self.watchlist = SQLAlchemyWatchlistRepository(self._session)
        self.custom_lists = SQLAlchemyCustomListRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        """Commit the active transaction."""
        assert self._session is not None, "UnitOfWork not started; use `async with`."
        await self._session.commit()

    async def rollback(self) -> None:
        """Roll back the active transaction."""
        assert self._session is not None, "UnitOfWork not started; use `async with`."
        await self._session.rollback()


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
