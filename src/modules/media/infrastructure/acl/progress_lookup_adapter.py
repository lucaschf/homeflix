"""Adapter that implements ``ProgressLookupPort`` using the Watch Progress UoW.

This is the only file in the Media BC that imports from the Watch
Progress BC. Above the adapter, the use cases only see
``ProgressSummary``.
"""

from collections.abc import Sequence

from src.modules.media.application.ports.progress_lookup_port import (
    ProgressLookupPort,
    ProgressSummary,
)
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)
from src.shared_kernel.value_objects.profile_id import ProfileId


class ProgressLookupAdapter(ProgressLookupPort):
    """Resolve progress snapshots via the Watch Progress Unit of Work."""

    def __init__(self, watch_progress_uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        self._watch_progress_uow_factory = watch_progress_uow_factory

    async def find_for_media_ids(
        self,
        media_ids: Sequence[str],
        *,
        profile_id: str,
    ) -> dict[str, ProgressSummary]:
        """Fetch progress rows scoped to the caller's profile."""
        if not media_ids:
            return {}
        profile = ProfileId(profile_id)
        async with self._watch_progress_uow_factory() as uow:
            progress_map = await uow.progress.find_by_media_ids(list(media_ids), profile)
        return {
            media_id: ProgressSummary(
                media_id=media_id,
                percentage=progress.percentage,
                position_seconds=progress.position_seconds,
                status=progress.status.value,
                last_watched_at=progress.last_watched_at,
            )
            for media_id, progress in progress_map.items()
        }


__all__ = ["ProgressLookupAdapter"]
