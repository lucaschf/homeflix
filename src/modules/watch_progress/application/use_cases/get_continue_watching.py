"""GetContinueWatchingUseCase - List in-progress items with media details."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.modules.watch_progress.application.dtos import (
    ContinueWatchingItem,
    ContinueWatchingOutput,
    GetContinueWatchingInput,
)
from src.modules.watch_progress.domain.services import ContinueWatchingSelector
from src.modules.watch_progress.domain.value_objects import (
    EpisodeCandidate,
    WatchableMediaType,
    WatchStatus,
)
from src.shared_kernel.episode_composite_id import EpisodeCompositeId

if TYPE_CHECKING:
    from datetime import datetime

    from src.modules.watch_progress.application.ports import (
        MediaLookupPort,
        SeriesWithEpisodesInfo,
    )
    from src.modules.watch_progress.domain.entities import WatchProgress
    from src.modules.watch_progress.domain.repositories import WatchProgressRepository

_logger = logging.getLogger(__name__)


class GetContinueWatchingUseCase:
    """List in-progress media items with display metadata.

    Joins progress records with movie/series data (via ``MediaLookupPort``)
    to provide title and poster for the "Continue Watching" UI section.

    For series, returns at most one item per series — the best episode
    to resume. The selection rule lives in
    ``ContinueWatchingSelector``; this use case only orchestrates
    loading data and projecting the selector's output into the DTO.

    Example:
        >>> use_case = GetContinueWatchingUseCase(progress_repo, media_lookup)
        >>> result = await use_case.execute(GetContinueWatchingInput(limit=10))
    """

    def __init__(
        self,
        progress_repository: WatchProgressRepository,
        media_lookup: MediaLookupPort,
        selector: ContinueWatchingSelector | None = None,
    ) -> None:
        """Initialize the use case.

        Args:
            progress_repository: Repository for watch progress.
            media_lookup: Port for resolving media display metadata.
            selector: Domain service that picks the best episode. The
                default is a fresh instance — callers only pass one in
                tests that want to stub selection.
        """
        self._progress_repo = progress_repository
        self._media_lookup = media_lookup
        self._selector = selector or ContinueWatchingSelector()

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
        """Fetch series metadata, build candidates, pick one, project to a DTO."""
        series = await self._media_lookup.get_series_with_episodes(series_id, lang)
        if not series:
            return None

        candidates = await self._build_candidates(series_id, series)
        if not candidates:
            return None

        selection = self._selector.pick(candidates)
        if selection.candidate is None:
            return None

        return self._build_series_item(series, selection.candidate, selection.latest_watched_at)

    async def _build_candidates(
        self,
        series_id: str,
        series: SeriesWithEpisodesInfo,
    ) -> list[EpisodeCandidate]:
        """Translate series episodes + their progress into selector inputs."""
        media_ids: list[str] = []
        episode_tuples: list[tuple[str, int, int, str, int]] = []

        for episode in series.episodes:
            mid = EpisodeCompositeId.build(
                series_id,
                episode.season_number,
                episode.episode_number,
            ).media_id
            media_ids.append(mid)
            episode_tuples.append(
                (
                    mid,
                    episode.season_number,
                    episode.episode_number,
                    episode.title,
                    episode.duration_seconds,
                )
            )

        if not episode_tuples:
            return []

        progress_map = await self._progress_repo.find_by_media_ids(media_ids)

        return [
            EpisodeCandidate(
                series_id=series_id,
                media_id=mid,
                season_number=season,
                episode_number=episode,
                episode_title=title,
                duration_seconds=duration,
                progress=progress_map.get(mid),
            )
            for mid, season, episode, title, duration in episode_tuples
        ]

    @staticmethod
    def _build_series_item(
        series: SeriesWithEpisodesInfo,
        candidate: EpisodeCandidate,
        fallback_last_watched: datetime | None = None,
    ) -> ContinueWatchingItem:
        """Project a ``(series, selected candidate)`` pair into the transport DTO."""
        progress = candidate.progress
        last_watched = (
            progress.last_watched_at.isoformat()
            if progress
            else (fallback_last_watched.isoformat() if fallback_last_watched else "")
        )

        return ContinueWatchingItem(
            media_id=candidate.media_id,
            media_type=WatchableMediaType.EPISODE,
            title=candidate.episode_title,
            poster_path=series.poster_path,
            backdrop_path=series.backdrop_path,
            position_seconds=progress.position_seconds if progress else 0,
            duration_seconds=(
                progress.duration_seconds if progress else candidate.duration_seconds
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
