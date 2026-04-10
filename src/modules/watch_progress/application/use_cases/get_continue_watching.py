"""GetContinueWatchingUseCase - List in-progress items with media details."""

from __future__ import annotations

import logging
from dataclasses import dataclass
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


@dataclass
class EpisodeCandidate:
    """An episode with its coordinates and optional progress."""

    series_id: str
    season_number: int
    episode_number: int
    media_id: str
    progress: WatchProgress | None


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

        candidates = await self._build_candidates(series_id, series)
        if not candidates:
            return None

        best, latest_watched_at = self._pick_series_episode(candidates)
        if not best:
            return None

        return self._build_series_item(series, best, lang, latest_watched_at)

    async def _build_candidates(
        self,
        series_id: str,
        series: Series,
    ) -> list[EpisodeCandidate]:
        """Build EpisodeCandidate list with progress for all episodes."""
        candidates: list[EpisodeCandidate] = []
        media_ids: list[str] = []

        for s in sorted(series.seasons, key=lambda s: s.season_number):
            for ep in sorted(s.episodes, key=lambda e: e.episode_number):
                mid = EpisodeCompositeId.build(
                    series_id,
                    s.season_number,
                    ep.episode_number,
                ).media_id
                media_ids.append(mid)
                candidates.append(
                    EpisodeCandidate(
                        series_id=series_id,
                        season_number=s.season_number,
                        episode_number=ep.episode_number,
                        media_id=mid,
                        progress=None,
                    )
                )

        if not candidates:
            return []

        progress_map = await self._progress_repo.find_by_media_ids(media_ids)
        for candidate in candidates:
            candidate.progress = progress_map.get(candidate.media_id)

        return candidates

    @staticmethod
    def _pick_series_episode(
        candidates: list[EpisodeCandidate],
    ) -> tuple[EpisodeCandidate | None, datetime | None]:
        """Pick the best episode to resume and the latest watched timestamp.

        Args:
            candidates: Ordered list of episode candidates with progress.

        Returns:
            Tuple of (best candidate, latest last_watched_at).
        """
        best_in_progress: EpisodeCandidate | None = None
        last_completed_idx: int | None = None
        latest_watched_at: datetime | None = None

        for idx, ep in enumerate(candidates):
            if not ep.progress:
                continue
            if not latest_watched_at or ep.progress.last_watched_at > latest_watched_at:
                latest_watched_at = ep.progress.last_watched_at

            if ep.progress.status == "in_progress":
                coords = (ep.season_number, ep.episode_number)
                if not best_in_progress or coords > (
                    best_in_progress.season_number,
                    best_in_progress.episode_number,
                ):
                    best_in_progress = ep
            elif ep.progress.status == "completed":
                last_completed_idx = max(last_completed_idx or -1, idx)

        if best_in_progress:
            return best_in_progress, latest_watched_at

        if last_completed_idx is not None:
            for ep in candidates[last_completed_idx + 1 :]:
                if ep.progress is None:
                    return ep, latest_watched_at

        return None, latest_watched_at

    def _build_series_item(
        self,
        series: Series,
        candidate: EpisodeCandidate,
        lang: str,
        fallback_last_watched: datetime | None = None,
    ) -> ContinueWatchingItem | None:
        """Build a ContinueWatchingItem from a resolved candidate.

        Args:
            series: The series entity.
            candidate: The selected episode candidate.
            lang: Language code.
            fallback_last_watched: Fallback timestamp for unwatched episodes.

        Returns:
            ContinueWatchingItem or None if episode not found in series.
        """
        season = series.get_season(candidate.season_number)
        if not season:
            return None
        episode = season.get_episode(candidate.episode_number)
        if not episode:
            return None

        progress = candidate.progress
        last_watched = (
            progress.last_watched_at.isoformat()
            if progress
            else (fallback_last_watched.isoformat() if fallback_last_watched else "")
        )

        return ContinueWatchingItem(
            media_id=candidate.media_id,
            media_type="episode",
            title=episode.title.value,
            poster_path=series.poster_path.value if series.poster_path else None,
            backdrop_path=series.backdrop_path.value if series.backdrop_path else None,
            position_seconds=progress.position_seconds if progress else 0,
            duration_seconds=progress.duration_seconds if progress else episode.duration.value,
            percentage=progress.percentage if progress else 0.0,
            last_watched_at=last_watched,
            series_id=str(series.id),
            series_title=series.get_title(lang),
            season_number=candidate.season_number,
            episode_number=candidate.episode_number,
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
