"""SQLAlchemy implementation of WatchProgressUnitOfWork."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.persistence.session_manager import create_tracked_session
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWork,
    WatchProgressUnitOfWorkFactory,
)
from src.modules.watch_progress.infrastructure.persistence.repositories.watch_progress_repository import (
    SQLAlchemyWatchProgressRepository,
)


class SqlAlchemyWatchProgressUnitOfWork(WatchProgressUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the watch_progress context."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError(
                "WatchProgressUnitOfWork is already active; nested use is not supported."
            )
        self._session = create_tracked_session(self._session_factory)
        self.progress = SQLAlchemyWatchProgressRepository(self._session)
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
            self._session = None

    async def commit(self) -> None:
        """Commit the active transaction."""
        assert self._session is not None, "UnitOfWork not started; use `async with`."
        await self._session.commit()

    async def rollback(self) -> None:
        """Roll back the active transaction."""
        assert self._session is not None, "UnitOfWork not started; use `async with`."
        await self._session.rollback()


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
