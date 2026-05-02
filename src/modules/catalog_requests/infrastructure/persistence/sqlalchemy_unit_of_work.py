"""SQLAlchemy implementation of ``CatalogRequestsUnitOfWork``."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWork,
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.catalog_requests.infrastructure.persistence.repositories import (
    SQLAlchemyCatalogRequestRepository,
)


class SqlAlchemyCatalogRequestsUnitOfWork(SqlAlchemyUnitOfWork, CatalogRequestsUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the catalog-requests BC."""

    def _build_repositories(self, session: AsyncSession) -> None:
        self.catalog_requests = SQLAlchemyCatalogRequestRepository(session)


class SqlAlchemyCatalogRequestsUnitOfWorkFactory(CatalogRequestsUnitOfWorkFactory):
    """Produce fresh ``SqlAlchemyCatalogRequestsUnitOfWork`` instances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> CatalogRequestsUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""
        return SqlAlchemyCatalogRequestsUnitOfWork(self._session_factory)


__all__ = [
    "SqlAlchemyCatalogRequestsUnitOfWork",
    "SqlAlchemyCatalogRequestsUnitOfWorkFactory",
]
