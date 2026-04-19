"""Adapter that implements ``MediaCountQueryPort`` using the Media UoW.

This is the only file in the Library BC that imports from the Media
BC. The port surface isolates the rest of Library from the Media
catalog — use cases depend only on ``MediaCountQueryPort``.
"""

from collections.abc import Sequence

from src.modules.library.application.ports.media_count_query_port import (
    MediaCountQueryPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory


class MediaCountQueryAdapter(MediaCountQueryPort):
    """Delegate count queries to the Media bounded context's Unit of Work."""

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def count_movies_under_paths(self, paths: Sequence[str]) -> int:
        """Delegate to ``MovieRepository.count_under_paths``."""
        async with self._media_uow_factory() as uow:
            return await uow.movies.count_under_paths(paths)

    async def count_series_under_paths(self, paths: Sequence[str]) -> int:
        """Delegate to ``SeriesRepository.count_under_paths``."""
        async with self._media_uow_factory() as uow:
            return await uow.series.count_under_paths(paths)


__all__ = ["MediaCountQueryAdapter"]
