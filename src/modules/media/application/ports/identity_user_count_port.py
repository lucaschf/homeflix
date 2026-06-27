"""Port for the cross-BC users count used by the admin overview.

The Overview dashboard shows a "users" card. That single count is the
only thing Media needs from Identity, so it reads through this port
instead of borrowing Identity's Unit of Work (ADR-009). The adapter
lives in ``media.infrastructure.acl``.
"""

from abc import ABC, abstractmethod


class IdentityUserCountPort(ABC):
    """Read the non-deleted user count from the Identity BC."""

    @abstractmethod
    async def count_users(self) -> int:
        """Return the number of active (non-deleted) users."""
        ...


__all__ = ["IdentityUserCountPort"]
