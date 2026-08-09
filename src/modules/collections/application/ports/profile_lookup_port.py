"""Port for resolving profile display names from the Identity BC.

Followed-list rows and shared-list previews show the *owner's* display
name ("shared by Lucas"). Collections doesn't own profile data — this
port is the surface through which it resolves a display name for one
or more owner profile ids. The adapter lives in
``collections.infrastructure.acl``.

See ADR-009 for the cross-BC read port pattern.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence


class ProfileLookupPort(ABC):
    """Batch lookup of profile display names by external id."""

    @abstractmethod
    async def get_names(self, profile_ids: Sequence[str]) -> dict[str, str]:
        """Resolve display names for the given profile ids.

        Args:
            profile_ids: Prefixed external ids (``prf_xxx``).

        Returns:
            Map from ``profile_id`` to display name. Ids that don't
            resolve to a profile are simply absent from the map — the
            caller decides how to render the gap.
        """
        ...


__all__ = ["ProfileLookupPort"]
