"""Unit of Work — transactional boundary around repository operations.

The Unit of Work (UoW) owns a single transaction and the repositories
that participate in it. Application code declares its transactional
intent by wrapping writes in ``async with uow: ...``; on clean exit the
UoW commits, on any exception it rolls back. Repositories stay free of
commit/rollback logic so the transaction boundary lives where the
business operation lives — the use case.

Each bounded context exposes its own UoW interface in its application
layer (subclassing this base) that advertises the repositories it can
compose. Infrastructure provides the concrete implementation.

See docs/adr/ for the motivation and the alternatives considered.
"""

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self


class UnitOfWork(ABC):
    """Abstract transactional boundary.

    Subclasses in each bounded context expose the concrete repository
    set they manage (e.g. ``MediaUnitOfWork.movies``). The base contract
    only spans the transaction lifecycle so every module enforces the
    same semantics: commit on clean exit, rollback on error, idempotent
    teardown.

    Typical use::

        async with self._uow as uow:
            movie = await uow.movies.find_by_id(movie_id)
            movie = movie.mark_unavailable()
            await uow.movies.save(movie)
        # commit happens here on success; rollback on exception
    """

    @abstractmethod
    async def __aenter__(self) -> Self:
        """Start the transaction and make repositories available."""

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Commit on clean exit, rollback on any exception."""

    @abstractmethod
    async def commit(self) -> None:
        """Persist all staged changes in this unit.

        Callable from inside the context for multi-commit scenarios
        (rare). The context manager will also commit automatically on
        clean exit — calling ``commit`` manually means the final exit
        has nothing left to do.
        """

    @abstractmethod
    async def rollback(self) -> None:
        """Discard all staged changes in this unit.

        Automatically invoked on exception inside the context manager.
        Available for explicit rollback on domain-driven conditions
        (e.g. a business rule violation detected mid-operation).
        """


__all__ = ["UnitOfWork"]
