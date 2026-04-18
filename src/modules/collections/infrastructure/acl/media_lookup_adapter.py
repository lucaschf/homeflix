"""Adapter that implements ``MediaLookupPort`` using Media repositories.

This is the only file in the Collections BC that imports from
``src.modules.media.domain``. Everything above it sees ``MediaSummary``.
"""

from collections.abc import Sequence

from src.modules.collections.application.ports.media_lookup_port import (
    MediaLookupPort,
    MediaSummary,
)
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import MovieId, SeriesId
from src.shared_kernel.value_objects import CollectionMediaType


class MediaLookupAdapter(MediaLookupPort):
    """Resolve media display data via the Media BC's repositories."""

    def __init__(
        self,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        self._movie_repo = movie_repository
        self._series_repo = series_repository

    async def get_many(
        self,
        movie_ids: Sequence[str],
        series_ids: Sequence[str],
        lang: str,
    ) -> dict[tuple[CollectionMediaType, str], MediaSummary]:
        """Batch-resolve display metadata via the Media repositories."""
        result: dict[tuple[CollectionMediaType, str], MediaSummary] = {}

        if movie_ids:
            movies_map = await self._movie_repo.find_by_ids(
                [MovieId(mid) for mid in movie_ids],
            )
            for media_id, movie in movies_map.items():
                result[(CollectionMediaType.MOVIE, media_id)] = MediaSummary(
                    media_id=media_id,
                    media_type=CollectionMediaType.MOVIE,
                    title=movie.get_title(lang),
                    poster_path=movie.poster_path.value if movie.poster_path else None,
                )

        if series_ids:
            series_map = await self._series_repo.find_by_ids(
                [SeriesId(sid) for sid in series_ids],
            )
            for media_id, series in series_map.items():
                result[(CollectionMediaType.SERIES, media_id)] = MediaSummary(
                    media_id=media_id,
                    media_type=CollectionMediaType.SERIES,
                    title=series.get_title(lang),
                    poster_path=series.poster_path.value if series.poster_path else None,
                )

        return result


__all__ = ["MediaLookupAdapter"]
