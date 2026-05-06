"""SQLAlchemy-backed Unit of Work base.

Centralizes the transaction lifecycle every bounded-context UoW shares:
open a session from the factory, build the context's repositories onto
it, commit on clean exit and roll back on exception, then close the
session unconditionally so the UoW is safe for non-HTTP callers.

Subclasses implement :meth:`_build_repositories` to attach the
repositories the bounded context exposes (``uow.movies``, ``uow.progress``,
etc.). Everything else — the nested-use guard, commit/rollback/close,
the manual ``commit`` / ``rollback`` helpers — lives here so behavior
stays consistent across modules and any future change (logging, retry
on serialization failure, instrumentation) lands in a single place.
"""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.application.unit_of_work import UnitOfWork


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Shared SQLAlchemy transaction lifecycle.

    Not intended to be instantiated directly — each bounded context
    defines its own ``XxxUnitOfWork`` interface (declaring its
    repositories) and a concrete class that combines that interface
    with this base via multiple inheritance.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError(
                f"{type(self).__name__} is already active; nested use is not supported."
            )
        self._session = self._session_factory()
        self._build_repositories(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is None:
                await session.commit()
            else:
                await session.rollback()
        finally:
            await session.close()
            self._session = None

    async def commit(self) -> None:
        """Commit the active transaction."""
        await self._require_session().commit()

    async def rollback(self) -> None:
        """Roll back the active transaction."""
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        """Return the active session or raise ``RuntimeError`` if not started.

        Replaces the previous ``assert`` guards: ``assert`` would be
        stripped under ``python -O``, leaving an ``AttributeError`` on
        the next call instead of a clear "you forgot ``async with``"
        message. ``RuntimeError`` is unconditional and explicit.
        """
        if self._session is None:
            raise RuntimeError(
                f"{type(self).__name__} not started; use `async with` before "
                "calling commit/rollback or accessing repositories."
            )
        return self._session

    def _build_repositories(self, session: AsyncSession) -> None:
        """Attach bounded-context repositories to ``self`` for this transaction.

        Called once per ``__aenter__`` with the freshly opened session.
        Subclasses assign each repository they expose (``self.movies =
        SQLAlchemyMovieRepository(session)``, etc.) — the base stays
        agnostic of which repos the context carries.
        """
        raise NotImplementedError


__all__ = ["SqlAlchemyUnitOfWork"]
