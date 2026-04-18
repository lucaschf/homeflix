"""Adapter that implements ``MediaCountQueryPort`` using Media repositories.

This is the only file in the Library BC that imports from
``src.modules.media.domain``. The port surface isolates the rest of
Library from the Media catalog.
"""

from collections.abc import Sequence

from src.modules.library.application.ports.media_count_query_port import (
    MediaCountQueryPort,
)
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository


class MediaCountQueryAdapter(MediaCountQueryPort):
    """Delegate count queries to the Media bounded context's repositories."""

    def __init__(
        self,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        self._movie_repo = movie_repository
        self._series_repo = series_repository

    async def count_movies_under_paths(self, paths: Sequence[str]) -> int:
        """Delegate to ``MovieRepository.count_under_paths``."""
        return await self._movie_repo.count_under_paths(paths)

    async def count_series_under_paths(self, paths: Sequence[str]) -> int:
        """Delegate to ``SeriesRepository.count_under_paths``."""
        return await self._series_repo.count_under_paths(paths)


__all__ = ["MediaCountQueryAdapter"]
