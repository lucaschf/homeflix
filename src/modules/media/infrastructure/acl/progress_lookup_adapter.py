"""Adapter that implements ``ProgressLookupPort`` using the Watch Progress UoW.

This is the only file in the Media BC that imports from the Watch
Progress BC. Above the adapter, the use cases only see
``ProgressSummary``.

Per ADR-010, watch_progress is now scoped per profile. The
``ProgressLookupPort`` interface still doesn't carry a profile
parameter (Media routes have not been refactored to thread
``profile_id`` through their use cases yet), so the adapter applies
``settings.watch_progress_default_profile_id`` to every query during
the transition. When the setting is unset, the adapter degrades
gracefully — every call returns an empty map so Media routes simply
do not enrich responses with progress information.

Once Media's use cases gain ``profile_id`` in their inputs (a follow-up
PR), the port and this adapter will gain a ``profile_id`` parameter
and the default fallback will be removed.
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

    def __init__(
        self,
        watch_progress_uow_factory: WatchProgressUnitOfWorkFactory,
        default_profile_id: str | None,
    ) -> None:
        self._watch_progress_uow_factory = watch_progress_uow_factory
        self._default_profile_id = default_profile_id

    async def find_for_media_ids(
        self,
        media_ids: Sequence[str],
    ) -> dict[str, ProgressSummary]:
        """Fetch progress rows scoped to the configured default profile.

        Returns an empty map when the default profile is unset so the
        consumer can still serve responses without progress
        enrichment during strict-mode rollout.
        """
        if not media_ids or self._default_profile_id is None:
            return {}
        profile_id = ProfileId(self._default_profile_id)
        async with self._watch_progress_uow_factory() as uow:
            progress_map = await uow.progress.find_by_media_ids(list(media_ids), profile_id)
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
