"""SQLAlchemy implementation of MediaUnitOfWork."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.persistence.session_manager import create_tracked_session
from src.modules.media.application.unit_of_work import (
    MediaUnitOfWork,
    MediaUnitOfWorkFactory,
)
from src.modules.media.infrastructure.persistence.repositories.movie_repository import (
    SQLAlchemyMovieRepository,
)
from src.modules.media.infrastructure.persistence.repositories.series_repository import (
    SQLAlchemySeriesRepository,
)


class SqlAlchemyMediaUnitOfWork(MediaUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the media bounded context.

    Each ``async with`` block opens a fresh session registered for the
    request-scoped cleanup middleware, instantiates the movie and
    series repositories on that session, and commits on success or
    rolls back on exception.

    Nesting is not supported — entering an already-open UoW raises
    ``RuntimeError`` rather than silently creating a parallel session.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("MediaUnitOfWork is already active; nested use is not supported.")
        self._session = create_tracked_session(self._session_factory)
        self.movies = SQLAlchemyMovieRepository(self._session)
        self.series = SQLAlchemySeriesRepository(self._session)
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
            # The request-scoped middleware closes tracked sessions, but
            # we reset our handle so the UoW instance could be reused in
            # a new ``async with`` block if the caller holds it.
            self._session = None

    async def commit(self) -> None:
        """Commit the active transaction."""
        assert self._session is not None, "UnitOfWork not started; use `async with`."
        await self._session.commit()

    async def rollback(self) -> None:
        """Roll back the active transaction."""
        assert self._session is not None, "UnitOfWork not started; use `async with`."
        await self._session.rollback()


class SqlAlchemyMediaUnitOfWorkFactory(MediaUnitOfWorkFactory):
    """Produce fresh :class:`SqlAlchemyMediaUnitOfWork` instances.

    Holds the app-scoped session factory and hands out one new UoW
    per call, so each transactional block starts with its own session.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> MediaUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""
        return SqlAlchemyMediaUnitOfWork(self._session_factory)


__all__ = [
    "SqlAlchemyMediaUnitOfWork",
    "SqlAlchemyMediaUnitOfWorkFactory",
]
