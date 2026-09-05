"""Port for reading a profile's recently watched titles.

The home hero (``GET /api/v1/featured``) recommends titles based on
what the profile already watched and never repeats a title the
profile has seen. Media doesn't own watch history — this port is the
only surface through which the featured use case reaches into the
Watch Progress BC. The adapter lives in ``media.infrastructure.acl``.

Episode-level progress rows are collapsed into their parent series
on the way out: the hero recommends *titles* (movies and series),
never individual episodes.

See ADR-009 for the cross-BC read port pattern.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WatchedTitle:
    """A movie or series the profile has watch history for.

    ``media_type`` and ``status`` are plain strings so consumers don't
    need to import Watch Progress enums.

    Attributes:
        media_id: Prefixed external id of the title — ``mov_xxx`` for
            movies or ``ser_xxx`` for series (episode rows are
            collapsed into their series).
        media_type: ``"movie"`` or ``"series"``.
        status: Watch status of the most recent progress row for the
            title (``"in_progress"`` or ``"completed"``).
        last_watched_at: Timestamp of the most recent progress row.
    """

    media_id: str
    media_type: str
    status: str
    last_watched_at: datetime


class WatchHistoryPort(ABC):
    """Recently watched titles for a profile, most recent first."""

    @abstractmethod
    async def list_recently_watched(
        self,
        profile_id: str,
        *,
        limit: int,
    ) -> list[WatchedTitle]:
        """Return the profile's most recently watched titles.

        Args:
            profile_id: Prefixed external id (``prf_xxx``) of the
                profile whose history to read.
            limit: Maximum number of distinct titles to return.

        Returns:
            Distinct titles ordered by ``last_watched_at`` descending.
            A profile with no history yields an empty list.
        """
        ...


__all__ = ["WatchHistoryPort", "WatchedTitle"]
