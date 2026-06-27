"""Adapter implementing ``IdentityUserCountPort`` via the Identity UoW.

Isolates the cross-BC users-count read for the admin overview so the
aggregator use case depends only on the local port, not Identity's Unit
of Work (ADR-009).
"""

from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.media.application.ports.identity_user_count_port import (
    IdentityUserCountPort,
)


class IdentityUserCountAdapter(IdentityUserCountPort):
    """Read the active users count through the Identity Unit of Work."""

    def __init__(self, identity_uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._identity_uow_factory = identity_uow_factory

    async def count_users(self) -> int:
        """Return ``users.count()`` from a short-lived Identity UoW."""
        async with self._identity_uow_factory() as uow:
            return await uow.users.count()


__all__ = ["IdentityUserCountAdapter"]
