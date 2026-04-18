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
from src.modules.watch_progress.domain.value_objects import WatchableMediaType, WatchStatus
from src.shared_kernel.episode_composite_id import EpisodeCompositeId

if TYPE_CHECKING:
    from datetime import datetime

    from src.modules.watch_progress.application.ports import (
        EpisodeInfo,
        MediaLookupPort,
        SeriesWithEpisodesInfo,
    )
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
    episode: EpisodeInfo
    progress: WatchProgress | None


class GetContinueWatchingUseCase:
    """List in-progress media items with display metadata.

    Joins progress records with movie/series data (via ``MediaLookupPort``)
    to provide title and poster for the "Continue Watching" UI section.

    For series, returns at most one item per series — the best episode
    to resume. If no episode is in-progress but the series has unwatched
    episodes after completed ones, the next unwatched episode is returned.

    Example:
        >>> use_case = GetContinueWatchingUseCase(progress_repo, media_lookup)
        >>> result = await use_case.execute(GetContinueWatchingInput(limit=10))
    """

    def __init__(
        self,
        progress_repository: WatchProgressRepository,
        media_lookup: MediaLookupPort,
    ) -> None:
        """Initialize the use case.

        Args:
            progress_repository: Repository for watch progress.
            media_lookup: Port for resolving media display metadata.
        """
        self._progress_repo = progress_repository
        self._media_lookup = media_lookup

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
            if progress.media_type == WatchableMediaType.MOVIE:
                if progress.status != WatchStatus.IN_PROGRESS:
                    continue
                item = await self._enrich_movie(progress, input_dto.lang)
                if item:
                    items.append(item)
            elif progress.media_type == WatchableMediaType.EPISODE:
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
        series = await self._media_lookup.get_series_with_episodes(series_id, lang)
        if not series:
            return None

        candidates = await self._build_candidates(series_id, series)
        if not candidates:
            return None

        best, latest_watched_at = self._pick_series_episode(candidates)
        if not best:
            return None

        return self._build_series_item(series, best, latest_watched_at)

    async def _build_candidates(
        self,
        series_id: str,
        series: SeriesWithEpisodesInfo,
    ) -> list[EpisodeCandidate]:
        """Build EpisodeCandidate list with progress for all episodes."""
        media_ids: list[str] = []
        candidates: list[EpisodeCandidate] = []

        for episode in series.episodes:
            mid = EpisodeCompositeId.build(
                series_id,
                episode.season_number,
                episode.episode_number,
            ).media_id
            media_ids.append(mid)
            candidates.append(
                EpisodeCandidate(
                    series_id=series_id,
                    season_number=episode.season_number,
                    episode_number=episode.episode_number,
                    media_id=mid,
                    episode=episode,
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

            if ep.progress.status == WatchStatus.IN_PROGRESS:
                coords = (ep.season_number, ep.episode_number)
                if not best_in_progress or coords > (
                    best_in_progress.season_number,
                    best_in_progress.episode_number,
                ):
                    best_in_progress = ep
            elif ep.progress.status == WatchStatus.COMPLETED:
                last_completed_idx = max(last_completed_idx or -1, idx)

        if best_in_progress:
            return best_in_progress, latest_watched_at

        if last_completed_idx is not None:
            for ep in candidates[last_completed_idx + 1 :]:
                if ep.progress is None:
                    return ep, latest_watched_at

        return None, latest_watched_at

    @staticmethod
    def _build_series_item(
        series: SeriesWithEpisodesInfo,
        candidate: EpisodeCandidate,
        fallback_last_watched: datetime | None = None,
    ) -> ContinueWatchingItem:
        """Build a ContinueWatchingItem from a resolved candidate.

        Args:
            series: The series metadata.
            candidate: The selected episode candidate.
            fallback_last_watched: Fallback timestamp for unwatched episodes.

        Returns:
            ContinueWatchingItem for the candidate.
        """
        progress = candidate.progress
        last_watched = (
            progress.last_watched_at.isoformat()
            if progress
            else (fallback_last_watched.isoformat() if fallback_last_watched else "")
        )

        return ContinueWatchingItem(
            media_id=candidate.media_id,
            media_type=WatchableMediaType.EPISODE,
            title=candidate.episode.title,
            poster_path=series.poster_path,
            backdrop_path=series.backdrop_path,
            position_seconds=progress.position_seconds if progress else 0,
            duration_seconds=(
                progress.duration_seconds if progress else candidate.episode.duration_seconds
            ),
            percentage=progress.percentage if progress else 0.0,
            last_watched_at=last_watched,
            series_id=series.series_id,
            series_title=series.title,
            season_number=candidate.season_number,
            episode_number=candidate.episode_number,
        )

    async def _enrich_movie(
        self,
        progress: WatchProgress,
        lang: str,
    ) -> ContinueWatchingItem | None:
        """Enrich a movie progress record with metadata."""
        movie = await self._media_lookup.get_movie(progress.media_id, lang)
        if not movie:
            return None
        return ContinueWatchingItem(
            media_id=progress.media_id,
            media_type=progress.media_type,
            title=movie.title,
            poster_path=movie.poster_path,
            backdrop_path=movie.backdrop_path,
            position_seconds=progress.position_seconds,
            duration_seconds=progress.duration_seconds,
            percentage=progress.percentage,
            last_watched_at=progress.last_watched_at.isoformat(),
        )


__all__ = ["GetContinueWatchingUseCase"]
