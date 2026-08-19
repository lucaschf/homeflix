"""Cross-BC read port resolving profile display names from identity.

For the admin now-playing panel's "who is watching" column. The adapter
lives in ``media.infrastructure.acl`` and reads the identity UoW
(ADR-009 — media never imports identity domain directly).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class ProfileSummaryPort(ABC):
    """Resolves profile ids to their display names."""

    @abstractmethod
    async def names_for(self, profile_ids: Sequence[str]) -> dict[str, str]:
        """Map each known profile id to its display name.

        Ids with no matching profile are omitted from the result.
        """


__all__ = ["ProfileSummaryPort"]
