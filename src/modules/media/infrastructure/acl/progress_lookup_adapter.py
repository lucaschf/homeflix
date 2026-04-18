"""Adapter that implements ``ProgressLookupPort`` using the Watch Progress repo.

This is the only file in the Media BC that imports from
``src.modules.watch_progress.domain``. Above the adapter, the use
cases only see ``ProgressSummary``.
"""

from collections.abc import Sequence

from src.modules.media.application.ports.progress_lookup_port import (
    ProgressLookupPort,
    ProgressSummary,
)
from src.modules.watch_progress.domain.repositories import WatchProgressRepository


class ProgressLookupAdapter(ProgressLookupPort):
    """Resolve progress snapshots via the Watch Progress repository."""

    def __init__(self, progress_repository: WatchProgressRepository) -> None:
        self._progress_repo = progress_repository

    async def find_for_media_ids(
        self,
        media_ids: Sequence[str],
    ) -> dict[str, ProgressSummary]:
        """Fetch progress rows and project each into a ``ProgressSummary``."""
        if not media_ids:
            return {}
        progress_map = await self._progress_repo.find_by_media_ids(list(media_ids))
        return {
            media_id: ProgressSummary(
                media_id=media_id,
                percentage=progress.percentage,
                position_seconds=progress.position_seconds,
                status=progress.status,
                last_watched_at=progress.last_watched_at,
            )
            for media_id, progress in progress_map.items()
        }


__all__ = ["ProgressLookupAdapter"]
