"""GetContinueWatchingUseCase - List in-progress items with media details."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.modules.watch_progress.application.dtos import (
    ContinueWatchingItem,
    ContinueWatchingOutput,
    GetContinueWatchingInput,
)
from src.shared_kernel.episode_composite_id import EpisodeCompositeId

if TYPE_CHECKING:
    from datetime import datetime

    from src.modules.media.domain.entities import Series
    from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
    from src.modules.watch_progress.domain.entities import WatchProgress
    from src.modules.watch_progress.domain.repositories import WatchProgressRepository

_logger = logging.getLogger(__name__)


class GetContinueWatchingUseCase:
    """List in-progress media items with display metadata.

    Joins progress records with movie/series data to provide title and
    poster for the "Continue Watching" UI section.

    For series, returns at most one item per series — the best episode
    to resume. If no episode is in-progress but the series has unwatched
    episodes after completed ones, the next unwatched episode is returned.

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
        progress_list = await self._progress_repo.list_recently_watched(limit=input_dto.limit)

        items: list[ContinueWatchingItem] = []
        seen_series: set[str] = set()

        for progress in progress_list:
            if progress.media_type == "movie":
                if progress.status != "in_progress":
                    continue
                item = await self._enrich_movie(progress, input_dto.lang)
                if item:
                    items.append(item)
            elif progress.media_type == "episode":
                parsed = EpisodeCompositeId.parse(progress.media_id)
                if not parsed or parsed.series_id in seen_series:
                    continue
                seen_series.add(parsed.series_id)
                item = await self._resolve_series_episode(
                    parsed.series_id,
                    input_dto.lang,
                )
                if item:
                    items.append(item)

        return ContinueWatchingOutput(items=items)

    async def _resolve_series_episode(
        self,
        series_id: str,
        lang: str,
    ) -> ContinueWatchingItem | None:
        """Find the best episode to resume for a series.

        Priority:
        1. Highest-numbered in-progress episode
        2. Next unwatched episode after the last completed one

        Args:
            series_id: External series ID.
            lang: Language code for localized metadata.

        Returns:
            ContinueWatchingItem for the best episode, or None.
        """
        from src.modules.media.domain.value_objects import SeriesId

        series = await self._series_repo.find_by_id(SeriesId(series_id))
        if not series:
            return None

        # Build composite IDs for all episodes and fetch progress in batch
        all_episodes = [
            (s.season_number, ep.episode_number)
            for s in sorted(series.seasons, key=lambda s: s.season_number)
            for ep in sorted(s.episodes, key=lambda e: e.episode_number)
        ]
        if not all_episodes:
            return None

        composite_ids = [
            EpisodeCompositeId.build(series_id, sn, en).media_id for sn, en in all_episodes
        ]
        progress_map = await self._progress_repo.find_by_media_ids(composite_ids)

        best_in_progress, last_completed = self._scan_episode_progress(
            series_id,
            all_episodes,
            progress_map,
        )

        target = best_in_progress or self._find_next_unwatched(
            series_id, all_episodes, progress_map, last_completed
        )
        if not target:
            return None

        # Use the most recent last_watched_at from any episode in the series
        # so the item sorts correctly even for "next unwatched" episodes
        latest_watched_at = max(
            (p.last_watched_at for p in progress_map.values()),
            default=None,
        )

        return self._build_series_item(
            series,
            target,
            progress_map,
            lang,
            fallback_last_watched=latest_watched_at,
        )

    @staticmethod
    def _scan_episode_progress(
        series_id: str,
        all_episodes: list[tuple[int, int]],
        progress_map: dict[str, WatchProgress],
    ) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
        """Scan episodes and return (highest in-progress, highest completed)."""
        best_in_progress: tuple[int, int] | None = None
        last_completed: tuple[int, int] | None = None
        for season_num, ep_num in all_episodes:
            key = EpisodeCompositeId.build(series_id, season_num, ep_num).media_id
            progress = progress_map.get(key)
            if not progress:
                continue
            coords = (season_num, ep_num)
            if progress.status == "in_progress" and (
                not best_in_progress or coords > best_in_progress
            ):
                best_in_progress = coords
            elif progress.status == "completed" and (not last_completed or coords > last_completed):
                last_completed = coords
        return best_in_progress, last_completed

    @staticmethod
    def _find_next_unwatched(
        series_id: str,
        all_episodes: list[tuple[int, int]],
        progress_map: dict[str, WatchProgress],
        last_completed: tuple[int, int] | None,
    ) -> tuple[int, int] | None:
        """Find the next unwatched episode after the last completed one."""
        if not last_completed:
            return None
        past_completed = False
        for season_num, ep_num in all_episodes:
            if (season_num, ep_num) == last_completed:
                past_completed = True
                continue
            if past_completed:
                key = EpisodeCompositeId.build(series_id, season_num, ep_num).media_id
                if key not in progress_map:
                    return (season_num, ep_num)
        return None

    def _build_series_item(
        self,
        series: Series,
        target: tuple[int, int],
        progress_map: dict[str, WatchProgress],
        lang: str,
        fallback_last_watched: datetime | None = None,
    ) -> ContinueWatchingItem | None:
        """Build a ContinueWatchingItem for a specific series episode.

        Args:
            series: The series entity.
            target: Tuple of (season_number, episode_number).
            progress_map: Map of composite IDs to progress.
            lang: Language code.
            fallback_last_watched: Fallback timestamp for unwatched episodes.

        Returns:
            ContinueWatchingItem or None if episode not found.
        """
        season_num, ep_num = target
        season = series.get_season(season_num)
        if not season:
            return None
        episode = season.get_episode(ep_num)
        if not episode:
            return None

        series_id = str(series.id)
        composite_id = EpisodeCompositeId.build(series_id, season_num, ep_num).media_id
        progress = progress_map.get(composite_id)

        last_watched = (
            progress.last_watched_at.isoformat()
            if progress
            else (fallback_last_watched.isoformat() if fallback_last_watched else "")
        )

        return ContinueWatchingItem(
            media_id=composite_id,
            media_type="episode",
            title=episode.title.value,
            poster_path=series.poster_path.value if series.poster_path else None,
            backdrop_path=series.backdrop_path.value if series.backdrop_path else None,
            position_seconds=progress.position_seconds if progress else 0,
            duration_seconds=progress.duration_seconds if progress else episode.duration.value,
            percentage=progress.percentage if progress else 0.0,
            last_watched_at=last_watched,
            series_id=series_id,
            series_title=series.get_title(lang),
            season_number=season_num,
            episode_number=ep_num,
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


__all__ = ["GetContinueWatchingUseCase"]
