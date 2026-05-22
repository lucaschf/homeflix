"""SQLAlchemy implementation of :class:`SettingsUnitOfWork`."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.infrastructure.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from src.modules.settings.application.unit_of_work import (
    SettingsUnitOfWork,
    SettingsUnitOfWorkFactory,
)
from src.modules.settings.infrastructure.persistence.repositories import (
    SQLAlchemySettingRepository,
)


class SqlAlchemySettingsUnitOfWork(SqlAlchemyUnitOfWork, SettingsUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the settings BC."""

    def _build_repositories(self, session: AsyncSession) -> None:
        self.settings = SQLAlchemySettingRepository(session)


class SqlAlchemySettingsUnitOfWorkFactory(SettingsUnitOfWorkFactory):
    """Produce fresh :class:`SqlAlchemySettingsUnitOfWork` instances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SettingsUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""
        return SqlAlchemySettingsUnitOfWork(self._session_factory)


__all__ = [
    "SqlAlchemySettingsUnitOfWork",
    "SqlAlchemySettingsUnitOfWorkFactory",
]
