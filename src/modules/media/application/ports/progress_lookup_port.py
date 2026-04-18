"""Port for reading watch-progress data alongside series episodes.

The ``GET /api/v1/series/{id}`` endpoint embeds each episode's
progress (percentage, position, status, last-watched timestamp) into
the response. Media doesn't own progress data — this port is the
only surface through which it reaches into the Watch Progress BC.
The adapter lives in ``media.infrastructure.acl``.

See ADR-009 for the cross-BC read port pattern.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProgressSummary:
    """Snapshot of progress values needed by the Series endpoint.

    ``status`` is a plain string (``"in_progress"``, ``"completed"``,
    ...) so consumers don't need to import the Watch Progress enum.

    Attributes:
        media_id: Composite episode media id (``epi_ser_<series>_<s>_<e>``).
        percentage: Watch percentage in the range ``[0, 100]``.
        position_seconds: Last known playback position in seconds.
        status: Watch status label.
        last_watched_at: Last update timestamp.
    """

    media_id: str
    percentage: float
    position_seconds: int
    status: str
    last_watched_at: datetime


class ProgressLookupPort(ABC):
    """Batch lookup of progress records by media id."""

    @abstractmethod
    async def find_for_media_ids(
        self,
        media_ids: Sequence[str],
    ) -> dict[str, ProgressSummary]:
        """Return progress summaries for the given media ids.

        Args:
            media_ids: Composite or standalone media ids to look up.

        Returns:
            Map keyed by ``media_id``. Ids without a matching progress
            row are simply absent from the map.
        """
        ...


__all__ = ["ProgressLookupPort", "ProgressSummary"]
