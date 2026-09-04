"""Adapter that implements ``WatchHistoryPort`` using the Watch Progress UoW.

Alongside ``ProgressLookupAdapter`` this is one of the only files in
the Media BC that imports from the Watch Progress BC. Above the
adapter, the featured use case only sees ``WatchedTitle``.
"""

from src.modules.media.application.ports.watch_history_port import (
    WatchedTitle,
    WatchHistoryPort,
)
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)
from src.modules.watch_progress.domain.entities import WatchProgress
from src.shared_kernel.value_objects.profile_id import ProfileId

# Several progress rows (one per episode) collapse into a single
# series title, so the raw window has to be wider than the number of
# titles the caller asked for. A binge of one show can easily fill
# dozens of rows.
_ROWS_PER_TITLE = 8
_MAX_ROWS = 500


class WatchHistoryAdapter(WatchHistoryPort):
    """Resolve recently watched titles via the Watch Progress Unit of Work."""

    def __init__(self, watch_progress_uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        self._watch_progress_uow_factory = watch_progress_uow_factory

    async def list_recently_watched(
        self,
        profile_id: str,
        *,
        limit: int,
    ) -> list[WatchedTitle]:
        """Fetch progress rows for the profile and collapse them into titles."""
        if limit <= 0:
            return []
        profile = ProfileId(profile_id)
        window = min(limit * _ROWS_PER_TITLE, _MAX_ROWS)
        async with self._watch_progress_uow_factory() as uow:
            rows = await uow.progress.list_recently_watched(profile, limit=window)
        return _collapse_into_titles(rows, limit)


def _collapse_into_titles(rows: list[WatchProgress], limit: int) -> list[WatchedTitle]:
    """Map progress rows (most recent first) to distinct titles.

    The first row seen for a title wins, so the returned ``status`` and
    ``last_watched_at`` reflect the most recent progress on it.
    """
    titles: dict[str, WatchedTitle] = {}
    for row in rows:
        if row.media_id.is_movie:
            media_id = str(row.media_id.as_movie_id())
            media_type = "movie"
        else:
            media_id = str(row.media_id.as_episode().series_id)
            media_type = "series"
        if media_id in titles:
            continue
        titles[media_id] = WatchedTitle(
            media_id=media_id,
            media_type=media_type,
            status=row.status.value,
            last_watched_at=row.last_watched_at,
        )
        if len(titles) >= limit:
            break
    return list(titles.values())


__all__ = ["WatchHistoryAdapter"]
