"""SQLAlchemy implementation of PreferencesUnitOfWork."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.preferences.application.unit_of_work import (
    PreferencesUnitOfWork,
    PreferencesUnitOfWorkFactory,
)
from src.modules.preferences.infrastructure.persistence.repositories import (
    SQLAlchemyPreferencesRepository,
)


class SqlAlchemyPreferencesUnitOfWork(PreferencesUnitOfWork):
    """SQLAlchemy-backed UoW for the preferences bounded context."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError(
                "PreferencesUnitOfWork is already active; nested use is not supported."
            )
        self._session = self._session_factory()
        self.preferences = SQLAlchemyPreferencesRepository(self._session)
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
