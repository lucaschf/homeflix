"""ACL adapter satisfying ``MediaPlaybackLookupPort`` via media use cases.

Quarantines the streaming→media dependency in one place (ADR-009). Rather
than re-read the catalog repositories — which would duplicate the
per-profile library ACL — it delegates to media's ``GetMovieByIdUseCase``
and ``GetSeriesByIdUseCase`` (which already enforce that ACL) and projects
their DTOs into the streaming playback projections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.media.application.dtos.movie_dtos import GetMovieByIdInput
from src.modules.media.application.dtos.series_dtos import GetSeriesByIdInput
from src.modules.streaming.application.ports.media_lookup_port import (
    EpisodePlaybackInfo,
    MediaPlaybackLookupPort,
    MoviePlaybackInfo,
)

if TYPE_CHECKING:
    from src.modules.media.application.use_cases.get_movie_by_id import (
        GetMovieByIdUseCase,
    )
    from src.modules.media.application.use_cases.get_series_by_id import (
        GetSeriesByIdUseCase,
    )


class MediaPlaybackLookupAdapter(MediaPlaybackLookupPort):
    """Resolve playback info by delegating to media's catalog use cases."""

    def __init__(
        self,
        get_movie_by_id: GetMovieByIdUseCase,
        get_series_by_id: GetSeriesByIdUseCase,
    ) -> None:
        self._get_movie_by_id = get_movie_by_id
        self._get_series_by_id = get_series_by_id

    async def find_movie(self, profile_id: str, movie_id: str) -> MoviePlaybackInfo:
        """Fetch the movie via the catalog use case and project it."""
        movie = await self._get_movie_by_id.execute(
            GetMovieByIdInput(profile_id=profile_id, movie_id=movie_id),
        )
        return MoviePlaybackInfo(
            file_path=movie.file_path,
            scrub_preview_path=movie.scrub_preview_path,
            title=movie.title,
            year=movie.year,
            resolution=movie.resolution,
            poster_path=movie.poster_path,
            duration_seconds=movie.duration_seconds,
        )

    async def find_episode(
        self,
        profile_id: str,
        series_id: str,
        season_number: int,
        episode_number: int,
    ) -> EpisodePlaybackInfo | None:
        """Fetch the series and project the matching episode, or ``None``."""
        series = await self._get_series_by_id.execute(
            GetSeriesByIdInput(profile_id=profile_id, series_id=series_id),
        )
        for season in series.seasons:
            if season.season_number != season_number:
                continue
            for episode in season.episodes:
                if episode.episode_number == episode_number:
                    return EpisodePlaybackInfo(
                        episode_id=episode.id,
                        file_path=episode.file_path,
                        scrub_preview_path=episode.scrub_preview_path,
                        title=episode.title,
                        duration_seconds=episode.duration_seconds,
                        segment_start_seconds=episode.segment_start_seconds,
                        segment_end_seconds=episode.segment_end_seconds,
                        series_title=series.title,
                    )
            break
        return None


__all__ = ["MediaPlaybackLookupAdapter"]
