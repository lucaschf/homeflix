"""GetContinueWatchingUseCase - List in-progress items with media details."""

import logging

from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.watch_progress.application.dtos import (
    ContinueWatchingItem,
    ContinueWatchingOutput,
    GetContinueWatchingInput,
)
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.repositories import WatchProgressRepository

_logger = logging.getLogger(__name__)


class GetContinueWatchingUseCase:
    """List in-progress media items with display metadata.

    Joins progress records with movie data to provide title and
    poster for the "Continue Watching" UI section.

    Example:
        >>> use_case = GetContinueWatchingUseCase(progress_repo, movie_repo)
        >>> result = await use_case.execute(GetContinueWatchingInput(limit=10))
    """

    def __init__(
        self,
        progress_repository: WatchProgressRepository,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        """Initialize the use case.

        Args:
            progress_repository: Repository for watch progress.
            movie_repository: Repository for movie metadata.
            series_repository: Repository for series metadata.
        """
        self._progress_repo = progress_repository
        self._movie_repo = movie_repository
        self._series_repo = series_repository

    async def execute(self, input_dto: GetContinueWatchingInput) -> ContinueWatchingOutput:
        """Execute the use case.

        Args:
            input_dto: Contains limit and language.

        Returns:
            ContinueWatchingOutput with items including media metadata.
        """
        progress_list = await self._progress_repo.list_in_progress(limit=input_dto.limit)
        _logger.info("Found %d in-progress items", len(progress_list))

        items: list[ContinueWatchingItem] = []
        for progress in progress_list:
            _logger.info(
                "Enriching progress: media_id=%s, media_type=%s",
                progress.media_id,
                progress.media_type,
            )
            item = await self._enrich_with_metadata(progress, input_dto.lang)
            if item:
                items.append(item)
            else:
                _logger.warning("Could not find media for progress: %s", progress.media_id)

        return ContinueWatchingOutput(items=items)

    async def _enrich_with_metadata(
        self,
        progress: WatchProgress,
        lang: str,
    ) -> ContinueWatchingItem | None:
        """Enrich a progress record with media metadata.

        Args:
            progress: The watch progress record.
            lang: Language code for localized metadata.

        Returns:
            ContinueWatchingItem with metadata, or None if media not found.
        """
        if progress.media_type == "movie":
            return await self._enrich_movie(progress, lang)
        if progress.media_type == "episode":
            return await self._enrich_episode(progress, lang)
        return None

    async def _enrich_movie(
        self,
        progress: WatchProgress,
        lang: str,
    ) -> ContinueWatchingItem | None:
        """Enrich a movie progress record with metadata."""
        from src.modules.media.domain.value_objects import MovieId

        movie = await self._movie_repo.find_by_id(MovieId(progress.media_id))
        if not movie:
            return None
        return ContinueWatchingItem(
            media_id=progress.media_id,
            media_type=progress.media_type,
            title=movie.get_title(lang),
            poster_path=movie.poster_path.value if movie.poster_path else None,
            backdrop_path=movie.backdrop_path.value if movie.backdrop_path else None,
            position_seconds=progress.position_seconds,
            duration_seconds=progress.duration_seconds,
            percentage=progress.percentage,
            last_watched_at=progress.last_watched_at.isoformat(),
        )

    async def _enrich_episode(
        self,
        progress: WatchProgress,
        lang: str,
    ) -> ContinueWatchingItem | None:
        """Enrich an episode progress record with series metadata.

        Supports two media_id formats:
        - Standard EpisodeId: ``epi_<12chars>``
        - Composite key: ``epi_<series_id>_<season>_<episode>``
        """
        parsed = self._parse_episode_media_id(progress.media_id)
        if not parsed:
            return None

        series_id_str, season_num, episode_num = parsed

        from src.modules.media.domain.value_objects import SeriesId

        series = await self._series_repo.find_by_id(SeriesId(series_id_str))
        if not series:
            return None

        season = series.get_season(season_num)
        if not season:
            return None

        episode = season.get_episode(episode_num)
        if not episode:
            return None

        return ContinueWatchingItem(
            media_id=progress.media_id,
            media_type=progress.media_type,
            title=episode.title.value,
            poster_path=series.poster_path.value if series.poster_path else None,
            backdrop_path=series.backdrop_path.value if series.backdrop_path else None,
            position_seconds=progress.position_seconds,
            duration_seconds=progress.duration_seconds,
            percentage=progress.percentage,
            last_watched_at=progress.last_watched_at.isoformat(),
            series_id=str(series.id),
            series_title=series.get_title(lang),
            season_number=season.season_number,
            episode_number=episode.episode_number,
        )

    @staticmethod
    def _parse_episode_media_id(
        media_id: str,
    ) -> tuple[str, int, int] | None:
        """Parse an episode media_id into (series_id, season, episode).

        Handles composite format ``epi_ser_XXXX_S_E``.

        Returns:
            Tuple of (series_id, season_number, episode_number) or None.
        """
        if not media_id.startswith("epi_ser_"):
            return None
        # epi_ser_Hy9VjMfILYZe_3_2 → parts after "epi_" = "ser_Hy9VjMfILYZe_3_2"
        rest = media_id[4:]  # "ser_Hy9VjMfILYZe_3_2"
        parts = rest.rsplit("_", 2)
        if len(parts) != 3:
            return None
        series_id_str, season_str, episode_str = parts
        try:
            return series_id_str, int(season_str), int(episode_str)
        except ValueError:
            return None


__all__ = ["GetContinueWatchingUseCase"]
