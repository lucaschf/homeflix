"""Adapter that implements ``MediaLookupPort`` using the Media UoW.

This is the only file in the Watch Progress BC that imports from the
Media BC. Above the adapter, the use cases only see
``MovieDisplayInfo`` / ``SeriesWithEpisodesInfo``.
"""

from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import MovieId, SeriesId
from src.modules.watch_progress.application.ports.media_lookup_port import (
    EpisodeInfo,
    MediaLookupPort,
    MovieDisplayInfo,
    SeriesWithEpisodesInfo,
)


class MediaLookupAdapter(MediaLookupPort):
    """Resolve media metadata via the Media BC's Unit of Work."""

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def get_movie(self, media_id: str, lang: str) -> MovieDisplayInfo | None:
        """Map a ``Movie`` entity to a display DTO, or ``None`` when absent."""
        async with self._media_uow_factory() as uow:
            movie = await uow.movies.find_by_id(MovieId(media_id))
        if movie is None:
            return None
        return MovieDisplayInfo(
            media_id=media_id,
            title=movie.get_title(lang),
            poster_path=movie.poster_path.value if movie.poster_path else None,
            backdrop_path=movie.backdrop_path.value if movie.backdrop_path else None,
        )

    async def get_series_with_episodes(
        self,
        series_id: str,
        lang: str,
    ) -> SeriesWithEpisodesInfo | None:
        """Flatten a ``Series`` into display + sorted-episode DTOs."""
        async with self._media_uow_factory() as uow:
            series = await uow.series.find_by_id(SeriesId(series_id))
        if series is None:
            return None

        episodes: list[EpisodeInfo] = []
        for season in sorted(series.seasons, key=lambda s: s.season_number.value):
            for episode in sorted(season.episodes, key=lambda e: e.episode_number.value):
                episodes.append(
                    EpisodeInfo(
                        season_number=season.season_number.value,
                        episode_number=episode.episode_number.value,
                        title=episode.title.value,
                        duration_seconds=episode.duration.value,
                    )
                )

        return SeriesWithEpisodesInfo(
            series_id=series_id,
            title=series.get_title(lang),
            poster_path=series.poster_path.value if series.poster_path else None,
            backdrop_path=series.backdrop_path.value if series.backdrop_path else None,
            episodes=episodes,
        )


__all__ = ["MediaLookupAdapter"]
