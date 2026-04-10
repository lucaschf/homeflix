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
from src.shared_kernel.episode_composite_id import EpisodeCompositeId

_logger = logging.getLogger(__name__)


class GetContinueWatchingUseCase:
    """List in-progress media items with display metadata.

    Joins progress records with movie/series data to provide title and
    poster for the "Continue Watching" UI section.

    Example:
        >>> use_case = GetContinueWatchingUseCase(progress_repo, movie_repo, series_repo)
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

    def _build_item(
        self,
        progress: WatchProgress,
        *,
        title: str,
        poster_path: str | None,
        backdrop_path: str | None,
        series_id: str | None = None,
        series_title: str | None = None,
        season_number: int | None = None,
        episode_number: int | None = None,
    ) -> ContinueWatchingItem:
        """Build a ContinueWatchingItem from progress and media metadata.

        Args:
            progress: The watch progress record.
            title: Display title.
            poster_path: Poster image path.
            backdrop_path: Backdrop image path.
            series_id: Series external ID (episodes only).
            series_title: Series title (episodes only).
            season_number: Season number (episodes only).
            episode_number: Episode number (episodes only).

        Returns:
            A fully populated ContinueWatchingItem.
        """
        return ContinueWatchingItem(
            media_id=progress.media_id,
            media_type=progress.media_type,
            title=title,
            poster_path=poster_path,
            backdrop_path=backdrop_path,
            position_seconds=progress.position_seconds,
            duration_seconds=progress.duration_seconds,
            percentage=progress.percentage,
            last_watched_at=progress.last_watched_at.isoformat(),
            series_id=series_id,
            series_title=series_title,
            season_number=season_number,
            episode_number=episode_number,
        )

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
        return self._build_item(
            progress,
            title=movie.get_title(lang),
            poster_path=movie.poster_path.value if movie.poster_path else None,
            backdrop_path=movie.backdrop_path.value if movie.backdrop_path else None,
        )

    async def _enrich_episode(
        self,
        progress: WatchProgress,
        lang: str,
    ) -> ContinueWatchingItem | None:
        """Enrich an episode progress record with series metadata.

        Parses the composite media_id format (``epi_ser_XXX_S_E``)
        to look up the series, season, and episode.
        """
        parsed = EpisodeCompositeId.parse(progress.media_id)
        if not parsed:
            return None

        from src.modules.media.domain.value_objects import SeriesId

        series = await self._series_repo.find_by_id(SeriesId(parsed.series_id))
        if not series:
            return None

        season = series.get_season(parsed.season_number)
        if not season:
            return None

        episode = season.get_episode(parsed.episode_number)
        if not episode:
            return None

        return self._build_item(
            progress,
            title=episode.title.value,
            poster_path=series.poster_path.value if series.poster_path else None,
            backdrop_path=series.backdrop_path.value if series.backdrop_path else None,
            series_id=str(series.id),
            series_title=series.get_title(lang),
            season_number=season.season_number,
            episode_number=episode.episode_number,
        )


__all__ = ["GetContinueWatchingUseCase"]
