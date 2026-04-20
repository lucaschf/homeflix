"""SQLAlchemy implementation of LibraryUnitOfWork."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.modules.library.application.unit_of_work import (
    LibraryUnitOfWork,
    LibraryUnitOfWorkFactory,
)
from src.modules.library.infrastructure.persistence.repositories.sqlalchemy_library_repository import (
    SqlAlchemyLibraryRepository,
)


class SqlAlchemyLibraryUnitOfWork(SqlAlchemyUnitOfWork, LibraryUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the library bounded context."""

    def _build_repositories(self, session: AsyncSession) -> None:
        self.libraries = SqlAlchemyLibraryRepository(session)


class SqlAlchemyLibraryUnitOfWorkFactory(LibraryUnitOfWorkFactory):
    """Produce fresh :class:`SqlAlchemyLibraryUnitOfWork` instances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> LibraryUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""
        return SqlAlchemyLibraryUnitOfWork(self._session_factory)


__all__ = [
    "SqlAlchemyLibraryUnitOfWork",
    "SqlAlchemyLibraryUnitOfWorkFactory",
]
