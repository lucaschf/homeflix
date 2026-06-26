"""Port for reading watch-progress fractions for collection items.

Watchlist and custom-list responses surface how far the caller has
watched each movie so the UI can draw a progress bar / "watched" badge.
Collections doesn't own progress data — this port is the only surface
through which it reaches into the Watch Progress BC. The adapter lives
in ``collections.infrastructure.acl``.

See ADR-009 for the cross-BC read port pattern.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence


class ProgressLookupPort(ABC):
    """Batch lookup of watch-progress fractions, scoped to a profile."""

    @abstractmethod
    async def get_progress(
        self,
        media_ids: Sequence[str],
        *,
        profile_id: str,
    ) -> dict[str, float]:
        """Return the watched fraction in ``[0, 1]`` per media id.

        Only ids with a progress row for the given profile are present;
        absent ids simply have no progress. Series progress lives on
        episodes (not surfaced here yet), so callers should pass movie
        ids only — a series id would resolve to nothing.

        Args:
            media_ids: Standalone media ids (``mov_xxx``) to look up.
            profile_id: Prefixed external id (``prf_xxx``) of the
                profile whose progress to read.

        Returns:
            Map keyed by ``media_id`` → watched fraction in ``[0, 1]``.
        """
        ...


__all__ = ["ProgressLookupPort"]
