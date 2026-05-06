"""Adapter that implements ``MediaLookupPort`` using the Media UoW.

This is the only file in the Collections BC that imports from the
Media BC. Everything above it sees ``MediaSummary``.
"""

from collections.abc import Sequence

from src.modules.collections.application.ports.media_lookup_port import (
    MediaLookupPort,
    MediaSummary,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import MovieId, SeriesId
from src.shared_kernel.value_objects import CollectionMediaType


class MediaLookupAdapter(MediaLookupPort):
    """Resolve media display data via the Media BC's Unit of Work."""

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def get_many(
        self,
        movie_ids: Sequence[str],
        series_ids: Sequence[str],
        lang: str,
    ) -> dict[tuple[CollectionMediaType, str], MediaSummary]:
        """Batch-resolve display metadata via a single Media UoW."""
        result: dict[tuple[CollectionMediaType, str], MediaSummary] = {}

        if not movie_ids and not series_ids:
            return result

        async with self._media_uow_factory() as uow:
            if movie_ids:
                movies_map = await uow.movies.find_by_ids(
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
                series_map = await uow.series.find_by_ids(
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
