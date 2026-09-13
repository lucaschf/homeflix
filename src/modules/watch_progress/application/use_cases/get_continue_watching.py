"""GetContinueWatchingUseCase - List in-progress items with media details."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.modules.watch_progress.application.dtos import (
    ContinueWatchingItem,
    ContinueWatchingOutput,
    GetContinueWatchingInput,
)
from src.modules.watch_progress.application.use_cases._title_gate import (
    find_visible_titles,
    title_of,
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
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from datetime import datetime

    from src.modules.watch_progress.application.ports import (
        MediaLookupPort,
        MovieDisplayInfo,
        ProfileViewingPolicyPort,
        SeriesWithEpisodesInfo,
    )
    from src.modules.watch_progress.application.unit_of_work import (
        WatchProgressUnitOfWork,
        WatchProgressUnitOfWorkFactory,
    )
    from src.modules.watch_progress.domain.entities import WatchProgress
    from src.modules.watch_progress.domain.repositories import RecentlyWatchedCursor
    from src.shared_kernel.content_policy import ViewingPolicy
    from src.shared_kernel.value_objects.media_id import MovieId, SeriesId

_logger = logging.getLogger(__name__)

#: Stored rows read per keyset page while filling the window. Matches the
#: route's ``limit`` ceiling, so a profile with no hidden titles is served
#: by a single page.
_PAGE_ROWS = 100


class GetContinueWatchingUseCase:
    """List in-progress media items with display metadata.

    Joins progress records with movie/series data (via ``MediaLookupPort``)
    to provide title and poster for the "Continue Watching" UI section.

    For series, returns at most one item per series — the best episode
    to resume. The selection rule lives in
    ``ContinueWatchingSelector``; this use case only orchestrates
    loading data and projecting the selector's output into the DTO.

    Only titles the caller's profile can see take part. ``limit`` is a
    window of the most recent progress *rows*, counted among visible rows
    only: a row whose title is missing or hidden — by library or by age —
    is skipped without using up the window, so the three cases produce
    the same list and a small ``limit`` cannot be used to tell them
    apart. The window is filled by keyset pages over the profile's own
    progress stream, never by offset.

    Example:
        >>> use_case = GetContinueWatchingUseCase(
        ...     uow_factory, media_lookup, profile_viewing_policy
        ... )
        >>> result = await use_case.execute(GetContinueWatchingInput(limit=10))
    """

    def __init__(
        self,
        uow_factory: WatchProgressUnitOfWorkFactory,
        media_lookup: MediaLookupPort,
        profile_viewing_policy: ProfileViewingPolicyPort,
        selector: ContinueWatchingSelector | None = None,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh watch progress UoW.
            media_lookup: Port for resolving title visibility and media
                display metadata.
            profile_viewing_policy: Port resolving the caller's viewing
                policy.
            selector: Domain service that picks the best episode. The
                default is a fresh instance — callers only pass one in
                tests that want to stub selection.
        """
        self._uow_factory = uow_factory
        self._media_lookup = media_lookup
        self._profile_viewing_policy = profile_viewing_policy
        self._selector = selector or ContinueWatchingSelector()

    async def execute(self, input_dto: GetContinueWatchingInput) -> ContinueWatchingOutput:
        """Execute the use case for the caller's profile."""
        profile_id = ProfileId(input_dto.profile_id)
        policy = await self._profile_viewing_policy.find_for_profile(profile_id)
        if policy.denies_everything:
            return ContinueWatchingOutput(items=[])

        window = await self._visible_window(profile_id, input_dto.limit, policy)

        # Completed movies use up their slot in the window but are never
        # shown, so they are not looked up either.
        movie_ids: dict[str, MovieId] = {}
        series_ids: dict[str, SeriesId] = {}
        for progress in window:
            if progress.media_type == WatchableMediaType.MOVIE:
                if progress.status == WatchStatus.IN_PROGRESS:
                    movie_id = progress.media_id.as_movie_id()
                    movie_ids[movie_id.value] = movie_id
            elif progress.media_type == WatchableMediaType.EPISODE:
                series_id = progress.media_id.as_episode().series_id
                series_ids[series_id.value] = series_id

        if not movie_ids and not series_ids:
            return ContinueWatchingOutput(items=[])

        # The full policy again: a title the visibility check let through
        # but the display query does not return is dropped (fail-closed).
        display = await self._media_lookup.find_display_info(
            movie_ids=list(movie_ids.values()),
            series_ids=list(series_ids.values()),
            lang=input_dto.lang,
            policy=policy,
        )

        items: list[ContinueWatchingItem] = []
        seen_series: set[SeriesId] = set()

        async with self._uow_factory() as uow:
            for progress in window:
                if progress.media_type == WatchableMediaType.MOVIE:
                    if progress.status != WatchStatus.IN_PROGRESS:
                        continue
                    movie = display.movies.get(progress.media_id.value)
                    if movie:
                        items.append(self._build_movie_item(progress, movie))
                elif progress.media_type == WatchableMediaType.EPISODE:
                    parsed = progress.media_id.as_episode()
                    if parsed.series_id in seen_series:
                        continue
                    seen_series.add(parsed.series_id)
                    item = await self._resolve_series_episode(
                        uow,
                        parsed.series_id,
                        display.series.get(parsed.series_id.value),
                        profile_id,
                    )
                    if item:
                        items.append(item)

        return ContinueWatchingOutput(items=items)

    async def _visible_window(
        self,
        profile_id: ProfileId,
        limit: int,
        policy: ViewingPolicy,
    ) -> list[WatchProgress]:
        """Collect the ``limit`` most recent rows whose title the policy reaches.

        Reads the profile's progress stream in keyset pages, each in its
        own short progress transaction, and asks the catalog once per page
        about the titles it has not judged yet. Rows are taken in stream
        order; a row is skipped without counting when its ``media_id`` was
        already taken (read again because its stored key changed under the
        cursor) or its title is missing or hidden.

        An autosave between pages cannot repeat a row: it moves the row
        above the cursor, into the part already read, so that row is left
        out of this response instead. That is acceptable for a list the
        next request rebuilds.

        Args:
            profile_id: The caller's profile.
            limit: Number of visible rows to collect.
            policy: The caller's viewing policy.

        Returns:
            Up to ``limit`` rows, most recent first.
        """
        window: list[WatchProgress] = []
        taken: set[str] = set()
        verdicts: dict[str, bool] = {}
        cursor: RecentlyWatchedCursor | None = None

        while len(window) < limit:
            async with self._uow_factory() as uow:
                page = await uow.progress.list_recently_watched_page(
                    profile_id, limit=_PAGE_ROWS, after=cursor
                )

            unjudged = {
                title.value: title
                for title in (title_of(progress.media_id) for progress in page.items)
                if title.value not in verdicts
            }
            if unjudged:
                visible = await find_visible_titles(self._media_lookup, unjudged.values(), policy)
                verdicts.update({key: key in visible for key in unjudged})

            for progress in page.items:
                if progress.media_id.value in taken:
                    continue
                if not verdicts[title_of(progress.media_id).value]:
                    continue
                taken.add(progress.media_id.value)
                window.append(progress)
                if len(window) == limit:
                    break

            if page.next_cursor is None:
                break
            cursor = page.next_cursor

        return window

    async def _resolve_series_episode(
        self,
        uow: WatchProgressUnitOfWork,
        series_id: SeriesId,
        series: SeriesWithEpisodesInfo | None,
        profile_id: ProfileId,
    ) -> ContinueWatchingItem | None:
        """Build candidates from loaded series metadata, pick one, project to a DTO."""
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
                    series_id,
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

    @staticmethod
    def _build_movie_item(
        progress: WatchProgress,
        movie: MovieDisplayInfo,
    ) -> ContinueWatchingItem:
        """Project a movie progress record and its display data into the DTO."""
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
