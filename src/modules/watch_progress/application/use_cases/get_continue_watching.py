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
from src.modules.watch_progress.domain.value_objects.watchable_media_id import (
    WatchableMediaId,
)
from src.shared_kernel.value_objects.episode_composite_id import EpisodeCompositeId
from src.shared_kernel.value_objects.media_id import SeriesId
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from datetime import datetime

    from src.modules.watch_progress.application.ports import (
        MediaLookupPort,
        SeriesWithEpisodesInfo,
    )
    from src.modules.watch_progress.application.unit_of_work import (
        WatchProgressUnitOfWork,
        WatchProgressUnitOfWorkFactory,
    )
    from src.modules.watch_progress.domain.entities import WatchProgress

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
        >>> use_case = GetContinueWatchingUseCase(uow_factory, media_lookup)
        >>> result = await use_case.execute(GetContinueWatchingInput(limit=10))
    """

    def __init__(
        self,
        uow_factory: WatchProgressUnitOfWorkFactory,
        media_lookup: MediaLookupPort,
        selector: ContinueWatchingSelector | None = None,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh watch progress UoW.
            media_lookup: Port for resolving media display metadata.
            selector: Domain service that picks the best episode. The
                default is a fresh instance — callers only pass one in
                tests that want to stub selection.
        """
        self._uow_factory = uow_factory
        self._media_lookup = media_lookup
        self._selector = selector or ContinueWatchingSelector()

    async def execute(self, input_dto: GetContinueWatchingInput) -> ContinueWatchingOutput:
        """Execute the use case for the caller's profile."""
        profile_id = ProfileId(input_dto.profile_id)
        items: list[ContinueWatchingItem] = []
        seen_series: set[str] = set()

        async with self._uow_factory() as uow:
            progress_list = await uow.progress.list_recently_watched(
                profile_id, limit=input_dto.limit
            )

            for progress in progress_list:
                if progress.media_type == WatchableMediaType.MOVIE:
                    if progress.status != WatchStatus.IN_PROGRESS:
                        continue
                    item = await self._enrich_movie(progress, input_dto.lang)
                    if item:
                        items.append(item)
                elif progress.media_type == WatchableMediaType.EPISODE:
                    parsed = progress.media_id.as_episode()
                    if parsed.series_id in seen_series:
                        continue
                    seen_series.add(parsed.series_id)
                    item = await self._resolve_series_episode(
                        uow,
                        SeriesId(parsed.series_id),
                        input_dto.lang,
                        profile_id,
                    )
                    if item:
                        items.append(item)

        return ContinueWatchingOutput(items=items)

    async def _resolve_series_episode(
        self,
        uow: WatchProgressUnitOfWork,
        series_id: SeriesId,
        lang: str,
        profile_id: ProfileId,
    ) -> ContinueWatchingItem | None:
        """Fetch series metadata, build candidates, pick one, project to a DTO."""
        series = await self._media_lookup.get_series_with_episodes(series_id, lang)
        if not series:
            return None

        candidates = await self._build_candidates(uow, series_id, series, profile_id)
        if not candidates:
            return None

        selection = self._selector.pick(candidates)
        if selection.candidate is None:
            return None

        return self._build_series_item(series, selection.candidate, selection.latest_watched_at)

    @staticmethod
    async def _build_candidates(
        uow: WatchProgressUnitOfWork,
        series_id: SeriesId,
        series: SeriesWithEpisodesInfo,
        profile_id: ProfileId,
    ) -> list[EpisodeCandidate]:
        """Translate series episodes + their progress into selector inputs.

        Candidate fields are kept flat (not composed with
        ``EpisodeInfo``) so the domain ``EpisodeCandidate`` does not
        transitively depend on an application-layer port DTO.
        """
        if not series.episodes:
            return []

        media_ids = [
            WatchableMediaId(
                EpisodeCompositeId.build(
                    series_id.value,
                    ep.season_number,
                    ep.episode_number,
                ).media_id
            )
            for ep in series.episodes
        ]

        progress_map = await uow.progress.find_by_media_ids(media_ids, profile_id)

        return [
            EpisodeCandidate(
                series_id=series_id.value,
                media_id=mid,
                season_number=ep.season_number,
                episode_number=ep.episode_number,
                episode_title=ep.title,
                duration_seconds=ep.duration_seconds,
                progress=progress_map.get(mid.value),
            )
            for ep, mid in zip(series.episodes, media_ids, strict=True)
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
            media_id=candidate.media_id.value,
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
        movie = await self._media_lookup.get_movie(progress.media_id.as_movie_id(), lang)
        if not movie:
            return None
        return ContinueWatchingItem(
            media_id=progress.media_id.value,
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
