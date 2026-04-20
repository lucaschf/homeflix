"""SQLAlchemy implementation of PreferencesUnitOfWork."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.modules.preferences.application.unit_of_work import (
    PreferencesUnitOfWork,
    PreferencesUnitOfWorkFactory,
)
from src.modules.preferences.infrastructure.persistence.repositories import (
    SQLAlchemyPreferencesRepository,
)


class SqlAlchemyPreferencesUnitOfWork(SqlAlchemyUnitOfWork, PreferencesUnitOfWork):
    """SQLAlchemy-backed UoW for the preferences bounded context."""

    def _build_repositories(self, session: AsyncSession) -> None:
        self.preferences = SQLAlchemyPreferencesRepository(session)


class SqlAlchemyPreferencesUnitOfWorkFactory(PreferencesUnitOfWorkFactory):
    """Produce fresh :class:`SqlAlchemyPreferencesUnitOfWork` instances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> PreferencesUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""
        return SqlAlchemyPreferencesUnitOfWork(self._session_factory)


__all__ = [
    "SqlAlchemyPreferencesUnitOfWork",
    "SqlAlchemyPreferencesUnitOfWorkFactory",
]
