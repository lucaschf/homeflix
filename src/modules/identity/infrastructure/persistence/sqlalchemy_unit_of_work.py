"""SQLAlchemy implementation of IdentityUnitOfWork."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.infrastructure.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from src.modules.identity.application.unit_of_work import (
    IdentityUnitOfWork,
    IdentityUnitOfWorkFactory,
)
from src.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyAccessTokenRepository,
    SqlAlchemyProfileRepository,
    SqlAlchemyUserRepository,
)


class SqlAlchemyIdentityUnitOfWork(SqlAlchemyUnitOfWork, IdentityUnitOfWork):
    """SQLAlchemy-backed Unit of Work for the identity bounded context."""

    def _build_repositories(self, session: AsyncSession) -> None:
        self.users = SqlAlchemyUserRepository(session)
        self.profiles = SqlAlchemyProfileRepository(session)
        self.access_tokens = SqlAlchemyAccessTokenRepository(session)


class SqlAlchemyIdentityUnitOfWorkFactory(IdentityUnitOfWorkFactory):
    """Produce fresh :class:`SqlAlchemyIdentityUnitOfWork` instances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> IdentityUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""
        return SqlAlchemyIdentityUnitOfWork(self._session_factory)


__all__ = [
    "SqlAlchemyIdentityUnitOfWork",
    "SqlAlchemyIdentityUnitOfWorkFactory",
]
