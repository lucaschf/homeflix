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
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId


class MediaLookupAdapter(MediaLookupPort):
    """Resolve media display data via the Media BC's Unit of Work."""

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def get_many(
        self,
        movie_ids: Sequence[MovieId],
        series_ids: Sequence[SeriesId],
        lang: str,
    ) -> dict[tuple[MediaType, str], MediaSummary]:
        """Batch-resolve display metadata via a single Media UoW."""
        result: dict[tuple[MediaType, str], MediaSummary] = {}

        if not movie_ids and not series_ids:
            return result

        async with self._media_uow_factory() as uow:
            if movie_ids:
                movies_map = await uow.movies.find_by_ids(list(movie_ids))
                for media_id, movie in movies_map.items():
                    best = movie.best_file
                    result[(MediaType.MOVIE, media_id)] = MediaSummary(
                        media_id=media_id,
                        media_type=MediaType.MOVIE,
                        title=movie.get_title(lang),
                        poster_path=movie.poster_path.value if movie.poster_path else None,
                        year=movie.year.value,
                        runtime_seconds=movie.duration.value or None,
                        genres=tuple(movie.get_genres(lang)),
                        resolution=best.resolution.value if best else None,
                        hdr=best.hdr_format is not None if best else False,
                    )

            if series_ids:
                series_map = await uow.series.find_by_ids(list(series_ids))
                for media_id, series in series_map.items():
                    # Runtime/resolution/HDR live on the series' episodes,
                    # which the batch lookup doesn't hydrate — left null
                    # (the client hides those fields when absent).
                    result[(MediaType.SERIES, media_id)] = MediaSummary(
                        media_id=media_id,
                        media_type=MediaType.SERIES,
                        title=series.get_title(lang),
                        poster_path=series.poster_path.value if series.poster_path else None,
                        year=series.start_year.value,
                        genres=tuple(series.get_genres(lang)),
                    )

        return result


__all__ = ["MediaLookupAdapter"]
