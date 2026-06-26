"""Adapter implementing ``ProgressLookupPort`` via the Watch Progress UoW.

This is the only file in the Collections BC that imports from the Watch
Progress BC for progress reads. Above it, use cases only see
``ProgressLookupPort``.
"""

from collections.abc import Sequence

from src.modules.collections.application.ports.progress_lookup_port import ProgressLookupPort
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)
from src.modules.watch_progress.domain.value_objects import WatchableMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


class ProgressLookupAdapter(ProgressLookupPort):
    """Resolve watched fractions via the Watch Progress Unit of Work."""

    def __init__(self, watch_progress_uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        self._watch_progress_uow_factory = watch_progress_uow_factory

    async def get_progress(
        self,
        media_ids: Sequence[str],
        *,
        profile_id: str,
    ) -> dict[str, float]:
        """Fetch watched fractions scoped to the caller's profile."""
        if not media_ids:
            return {}
        profile = ProfileId(profile_id)
        typed_ids = [WatchableMediaId(media_id) for media_id in media_ids]
        async with self._watch_progress_uow_factory() as uow:
            progress_map = await uow.progress.find_by_media_ids(typed_ids, profile)
        return {
            media_id: progress.percentage / 100.0 for media_id, progress in progress_map.items()
        }


__all__ = ["ProgressLookupAdapter"]
