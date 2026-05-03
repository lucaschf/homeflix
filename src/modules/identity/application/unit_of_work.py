"""Identity bounded-context Unit of Work interface."""

from abc import ABC, abstractmethod

from src.building_blocks.application.unit_of_work import UnitOfWork
from src.modules.identity.domain.repositories import (
    AccessTokenRepository,
    ProfileRepository,
    UserRepository,
)


class IdentityUnitOfWork(UnitOfWork):
    """Transactional boundary for identity aggregate operations.

    Subclasses populate ``users``, ``profiles`` and ``access_tokens``
    on ``__aenter__`` so writes within the same ``async with`` block
    share a single transaction (e.g. switching profile + updating
    session state in one atomic step).
    """

    users: UserRepository
    profiles: ProfileRepository
    access_tokens: AccessTokenRepository


class IdentityUnitOfWorkFactory(ABC):
    """Builds fresh ``IdentityUnitOfWork`` instances on demand."""

    @abstractmethod
    def __call__(self) -> IdentityUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""


__all__ = ["IdentityUnitOfWork", "IdentityUnitOfWorkFactory"]
