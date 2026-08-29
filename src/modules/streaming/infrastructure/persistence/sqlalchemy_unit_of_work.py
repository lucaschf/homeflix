"""SQLAlchemy implementation of StreamingUnitOfWork."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.modules.streaming.application.unit_of_work import (
    StreamingUnitOfWork,
    StreamingUnitOfWorkFactory,
)
from src.modules.streaming.infrastructure.persistence.repositories.subtitle_ocr_run_repository import (
    SqlAlchemySubtitleOcrRunRepository,
)


class SqlAlchemyStreamingUnitOfWork(SqlAlchemyUnitOfWork, StreamingUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the streaming bounded context.

    Exposes the ``subtitle_ocr_runs`` repository bound to the active
    transaction. Lifecycle (session open/commit/rollback/close, nested-use
    guard) lives in :class:`SqlAlchemyUnitOfWork`.
    """

    def _build_repositories(self, session: AsyncSession) -> None:
        self.subtitle_ocr_runs = SqlAlchemySubtitleOcrRunRepository(session)


class SqlAlchemyStreamingUnitOfWorkFactory(StreamingUnitOfWorkFactory):
    """Produce fresh :class:`SqlAlchemyStreamingUnitOfWork` instances.

    Holds the app-scoped session factory and hands out one new UoW per
    call, so each transactional block starts with its own session.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> StreamingUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""
        return SqlAlchemyStreamingUnitOfWork(self._session_factory)


__all__ = [
    "SqlAlchemyStreamingUnitOfWork",
    "SqlAlchemyStreamingUnitOfWorkFactory",
]
