"""SQLAlchemy implementation of MediaUnitOfWork."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
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


class SqlAlchemyMediaUnitOfWork(SqlAlchemyUnitOfWork, MediaUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the media bounded context.

    Exposes ``movies`` and ``series`` repositories bound to the active
    transaction. Lifecycle (session open/commit/rollback/close,
    nested-use guard) lives in :class:`SqlAlchemyUnitOfWork`.
    """

    def _build_repositories(self, session: AsyncSession) -> None:
        self.movies = SQLAlchemyMovieRepository(session)
        self.series = SQLAlchemySeriesRepository(session)


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
