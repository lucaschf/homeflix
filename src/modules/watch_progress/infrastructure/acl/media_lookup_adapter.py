"""Adapter that implements ``MediaLookupPort`` using the Media UoW.

This is the only file in the Watch Progress BC that imports from the
Media BC. Above the adapter, the use cases only see external ids and
``MovieDisplayInfo`` / ``SeriesWithEpisodesInfo``.

Every call hands the caller's policy to Media, which applies it in SQL
through the catalog visibility funnel — the adapter never filters on its
own, so it cannot drift from what the catalog shows.
"""

from collections.abc import Sequence

from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.watch_progress.application.ports.media_lookup_port import (
    EpisodeInfo,
    MediaDisplayBatch,
    MediaLookupPort,
    MovieDisplayInfo,
    SeriesWithEpisodesInfo,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId


class MediaLookupAdapter(MediaLookupPort):
    """Resolve media visibility and metadata via the Media BC's Unit of Work."""

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def find_visible_titles(
        self,
        *,
        movie_ids: Sequence[MovieId],
        series_ids: Sequence[SeriesId],
        policy: ViewingPolicy,
    ) -> frozenset[str]:
        """Read access off the catalog columns alone, without loading titles."""
        async with self._media_uow_factory() as uow:
            movies = await uow.catalog_access.find_movie_access(movie_ids, policy=policy)
            series = await uow.catalog_access.find_series_access(series_ids, policy=policy)
        return frozenset(movies) | frozenset(series)

    async def find_display_info(
        self,
        *,
        movie_ids: Sequence[MovieId],
        series_ids: Sequence[SeriesId],
        lang: str,
        policy: ViewingPolicy,
    ) -> MediaDisplayBatch:
        """Map visible movies and series, episodes sorted, to display DTOs."""
        async with self._media_uow_factory() as uow:
            movies = await uow.movies.find_by_ids(movie_ids, policy=policy)
            series = await uow.series.find_by_ids(series_ids, policy=policy)

        series_infos: dict[str, SeriesWithEpisodesInfo] = {}
        for series_id, entity in series.items():
            episodes = [
                EpisodeInfo(
                    season_number=season.season_number.value,
                    episode_number=episode.episode_number.value,
                    title=episode.get_title(lang),
                    duration_seconds=episode.duration.value,
                )
                for season in sorted(entity.seasons, key=lambda s: s.season_number.value)
                for episode in sorted(season.episodes, key=lambda e: e.episode_number.value)
            ]
            series_infos[series_id] = SeriesWithEpisodesInfo(
                series_id=series_id,
                title=entity.get_title(lang),
                poster_path=entity.get_poster_path(lang),
                backdrop_path=entity.get_backdrop_path(lang),
                episodes=episodes,
            )

        return MediaDisplayBatch(
            movies={
                movie_id: MovieDisplayInfo(
                    media_id=movie_id,
                    title=movie.get_title(lang),
                    poster_path=movie.get_poster_path(lang),
                    backdrop_path=movie.get_backdrop_path(lang),
                )
                for movie_id, movie in movies.items()
            },
            series=series_infos,
        )


__all__ = ["MediaLookupAdapter"]
