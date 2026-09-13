"""Adapter that implements ``MediaLookupPort`` using the Media UoW.

This is the only file in the Collections BC that imports from the
Media BC. Everything above it sees ``MediaSummary`` and external ids.
"""

from collections.abc import Sequence

from src.modules.collections.application.ports.media_lookup_port import (
    MediaLookupPort,
    MediaSummary,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.shared_kernel.content_policy import ViewingPolicy
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

        # ``policy=None`` on purpose: the use cases apply the caller's
        # viewing policy in Python, because they must tell a title hidden
        # from the caller (counted or silently dropped) apart from one
        # removed from the catalog (skipped) — a filtered query would
        # return both as absent.
        async with self._media_uow_factory() as uow:
            if movie_ids:
                movies_map = await uow.movies.find_by_ids(list(movie_ids), policy=None)
                for media_id, movie in movies_map.items():
                    best = movie.best_file
                    result[(MediaType.MOVIE, media_id)] = MediaSummary(
                        media_id=media_id,
                        media_type=MediaType.MOVIE,
                        title=movie.get_title(lang),
                        poster_path=movie.get_poster_path(lang),
                        year=movie.year.value,
                        runtime_seconds=movie.duration.value or None,
                        genres=tuple(movie.get_genres(lang)),
                        resolution=best.resolution.value if best else None,
                        hdr=best.hdr_format is not None if best else False,
                        library_id=movie.library_id,
                        minimum_age=movie.minimum_age,
                    )

            if series_ids:
                series_map = await uow.series.find_by_ids(list(series_ids), policy=None)
                for media_id, series in series_map.items():
                    # Runtime/resolution/HDR live on the series' episodes,
                    # which the batch lookup doesn't hydrate — left null
                    # (the client hides those fields when absent).
                    result[(MediaType.SERIES, media_id)] = MediaSummary(
                        media_id=media_id,
                        media_type=MediaType.SERIES,
                        title=series.get_title(lang),
                        poster_path=series.get_poster_path(lang),
                        year=series.start_year.value,
                        genres=tuple(series.get_genres(lang)),
                        library_id=series.library_id,
                        minimum_age=series.minimum_age,
                    )

        return result

    async def find_visible_titles(
        self,
        *,
        movie_ids: Sequence[MovieId],
        series_ids: Sequence[SeriesId],
        policy: ViewingPolicy,
    ) -> frozenset[str]:
        """Read access off the catalog columns alone, without loading titles.

        The policy goes to Media whole, which applies it in SQL through
        the catalog visibility funnel — nothing is filtered here.
        """
        async with self._media_uow_factory() as uow:
            movies = await uow.catalog_access.find_movie_access(movie_ids, policy=policy)
            series = await uow.catalog_access.find_series_access(series_ids, policy=policy)
        return frozenset(movies) | frozenset(series)


__all__ = ["MediaLookupAdapter"]
