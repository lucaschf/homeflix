"""Tests for GetContinueWatchingUseCase - visibility window, enrichment and deduplication."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, call

import pytest

from src.modules.watch_progress.application.dtos import (
    ContinueWatchingItem,
    GetContinueWatchingInput,
)
from src.modules.watch_progress.application.ports import (
    EpisodeInfo,
    MediaDisplayBatch,
    MediaLookupPort,
    MovieDisplayInfo,
    ProfileViewingPolicyPort,
    SeriesWithEpisodesInfo,
)
from src.modules.watch_progress.application.use_cases import GetContinueWatchingUseCase
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.repositories import (
    RecentlyWatchedCursor,
    RecentlyWatchedPage,
)
from src.modules.watch_progress.domain.value_objects import (
    PlaybackPosition,
    WatchableMediaType,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.watch_progress.unit.conftest import (
    WatchProgressUoWMocks,
    make_watch_progress_uow_mock,
)

_PROFILE_ID = ProfileId("prf_test12345678")
_LIBRARY_ID = "lib_test12345678"
_POLICY = ViewingPolicy.unrestricted([_LIBRARY_ID])

_MOVIE_A = "mov_aaaaaaaaaaaa"
_MOVIE_B = "mov_bbbbbbbbbbbb"
_MOVIE_C = "mov_cccccccccccc"
_MOVIE_HIDDEN = "mov_hhhhhhhhhhhh"
_MOVIE_MISSING = "mov_xxxxxxxxxxxx"
_BASE_TIME = datetime(2026, 4, 9, tzinfo=UTC)


def _input(*, limit: int = 10, lang: str = "en") -> GetContinueWatchingInput:
    """Build the use case input scoped to the test profile."""
    return GetContinueWatchingInput(profile_id=_PROFILE_ID.value, limit=limit, lang=lang)


def _make_progress(
    media_id: str,
    media_type: WatchableMediaType = WatchableMediaType.EPISODE,
    *,
    status: str = "in_progress",
    position: int = 1800,
    last_watched: datetime | None = None,
) -> WatchProgress:
    """Create a WatchProgress entity for testing."""
    return WatchProgress(
        profile_id=_PROFILE_ID,
        media_id=media_id,
        media_type=media_type,
        position=PlaybackPosition(position_seconds=position, duration_seconds=3600),
        status=status,
        last_watched_at=last_watched or _BASE_TIME,
    )


def _movie_progress(media_id: str, *, status: str = "in_progress") -> WatchProgress:
    return _make_progress(media_id, WatchableMediaType.MOVIE, status=status)


def _make_series_info(
    series_id: str,
    episodes_per_season: dict[int, list[int]],
    title: str = "Test Series",
) -> SeriesWithEpisodesInfo:
    episodes: list[EpisodeInfo] = []
    for season_num in sorted(episodes_per_season):
        for ep_num in sorted(episodes_per_season[season_num]):
            episodes.append(
                EpisodeInfo(
                    season_number=season_num,
                    episode_number=ep_num,
                    title=f"Episode {ep_num}",
                    duration_seconds=3600,
                )
            )
    return SeriesWithEpisodesInfo(
        series_id=series_id,
        title=title,
        poster_path=None,
        backdrop_path=None,
        episodes=episodes,
    )


def _movie_info(media_id: str, title: str | None = None) -> MovieDisplayInfo:
    return MovieDisplayInfo(
        media_id=media_id,
        title=title or f"Movie {media_id}",
        poster_path=f"/p/{media_id}.jpg",
        backdrop_path=f"/b/{media_id}.jpg",
    )


def _cursor(media_id: str) -> RecentlyWatchedCursor:
    return RecentlyWatchedCursor(last_watched_at=_BASE_TIME, media_id=media_id)


@dataclass
class _FakeCatalog:
    """Stand-in for the Media catalog behind ``MediaLookupPort``.

    ``hidden`` titles exist but the policy denies them; titles missing
    from ``movies`` / ``series`` do not exist. Both answer as absent.
    ``undisplayable`` titles pass the visibility check but are not
    returned by the display query.
    """

    movies: dict[str, MovieDisplayInfo] = field(default_factory=dict)
    series: dict[str, SeriesWithEpisodesInfo] = field(default_factory=dict)
    hidden: set[str] = field(default_factory=set)
    undisplayable: set[str] = field(default_factory=set)

    def _reachable(self, title_id: str) -> bool:
        return (title_id in self.movies or title_id in self.series) and title_id not in self.hidden

    async def find_visible_titles(
        self,
        *,
        movie_ids: Sequence[MovieId],
        series_ids: Sequence[SeriesId],
        policy: ViewingPolicy,
    ) -> frozenset[str]:
        requested = [m.value for m in movie_ids] + [s.value for s in series_ids]
        return frozenset(title_id for title_id in requested if self._reachable(title_id))

    async def find_display_info(
        self,
        *,
        movie_ids: Sequence[MovieId],
        series_ids: Sequence[SeriesId],
        lang: str,
        policy: ViewingPolicy,
    ) -> MediaDisplayBatch:
        def shown(title_id: str) -> bool:
            return self._reachable(title_id) and title_id not in self.undisplayable

        return MediaDisplayBatch(
            movies={m.value: self.movies[m.value] for m in movie_ids if shown(m.value)},
            series={s.value: self.series[s.value] for s in series_ids if shown(s.value)},
        )


@dataclass
class _Harness:
    """Mocks wired into one use case under test."""

    uow: WatchProgressUoWMocks
    media_lookup: AsyncMock
    policy_port: AsyncMock
    catalog: _FakeCatalog

    def use_case(self) -> GetContinueWatchingUseCase:
        return GetContinueWatchingUseCase(
            uow_factory=self.uow.factory,
            media_lookup=self.media_lookup,
            profile_viewing_policy=self.policy_port,
        )

    def stream(self, *pages: RecentlyWatchedPage) -> None:
        """Serve these pages in order; reading past the last one fails the test."""
        remaining = list(pages)

        async def next_page(
            profile_id: ProfileId,
            *,
            limit: int,
            after: RecentlyWatchedCursor | None,
        ) -> RecentlyWatchedPage:
            if not remaining:
                raise AssertionError("read past the end of the progress stream")
            return remaining.pop(0)

        self.uow.progress.list_recently_watched_page.side_effect = next_page

    def single_page(self, rows: list[WatchProgress]) -> None:
        self.stream(RecentlyWatchedPage(items=rows, next_cursor=None))


def _make_harness(policy: ViewingPolicy = _POLICY) -> _Harness:
    catalog = _FakeCatalog()
    media_lookup = AsyncMock(spec=MediaLookupPort)
    media_lookup.find_visible_titles.side_effect = catalog.find_visible_titles
    media_lookup.find_display_info.side_effect = catalog.find_display_info
    policy_port = AsyncMock(spec=ProfileViewingPolicyPort)
    policy_port.find_for_profile.return_value = policy
    return _Harness(
        uow=make_watch_progress_uow_mock(),
        media_lookup=media_lookup,
        policy_port=policy_port,
        catalog=catalog,
    )


@pytest.fixture()
def harness() -> _Harness:
    return _make_harness()


def _ids(items: list[ContinueWatchingItem]) -> list[str]:
    return [item.media_id for item in items]


class TestEnrichEpisode:
    """Tests for episode enrichment in continue watching."""

    @pytest.mark.asyncio
    async def test_enrich_valid_composite_episode(self, harness):
        harness.catalog.series["ser_Hy9VjMfILYZe"] = _make_series_info("ser_Hy9VjMfILYZe", {3: [2]})
        progress = _make_progress("epi_ser_Hy9VjMfILYZe_3_2")
        harness.single_page([progress])
        harness.uow.progress.find_by_media_ids.return_value = {
            "epi_ser_Hy9VjMfILYZe_3_2": progress,
        }

        result = await harness.use_case().execute(_input())

        assert len(result.items) == 1
        item = result.items[0]
        assert isinstance(item, ContinueWatchingItem)
        assert item.series_id == "ser_Hy9VjMfILYZe"
        assert item.series_title == "Test Series"
        assert item.season_number == 3
        assert item.episode_number == 2

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_missing_series(self, harness):
        harness.single_page([_make_progress("epi_ser_NotExists123_1_1")])

        result = await harness.use_case().execute(_input())
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_missing_season(self, harness):
        harness.catalog.series["ser_Hy9VjMfILYZe"] = _make_series_info("ser_Hy9VjMfILYZe", {3: [2]})
        progress = _make_progress("epi_ser_Hy9VjMfILYZe_99_1")
        harness.single_page([progress])
        harness.uow.progress.find_by_media_ids.return_value = {
            "epi_ser_Hy9VjMfILYZe_99_1": progress,
        }

        result = await harness.use_case().execute(_input())
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_missing_episode(self, harness):
        harness.catalog.series["ser_Hy9VjMfILYZe"] = _make_series_info("ser_Hy9VjMfILYZe", {3: [2]})
        progress = _make_progress("epi_ser_Hy9VjMfILYZe_3_99")
        harness.single_page([progress])
        harness.uow.progress.find_by_media_ids.return_value = {
            "epi_ser_Hy9VjMfILYZe_3_99": progress,
        }

        result = await harness.use_case().execute(_input())
        assert len(result.items) == 0


class TestEnrichMovie:
    """The movie branch projects progress and display data into the card."""

    @pytest.mark.asyncio
    async def test_in_progress_movie_is_enriched(self, harness):
        harness.catalog.movies[_MOVIE_A] = _movie_info(_MOVIE_A, "Inception")
        progress = _make_progress(
            _MOVIE_A,
            WatchableMediaType.MOVIE,
            position=900,
            last_watched=datetime(2026, 4, 10, 21, 30, tzinfo=UTC),
        )
        harness.single_page([progress])

        result = await harness.use_case().execute(_input())

        assert result.items == [
            ContinueWatchingItem(
                media_id=_MOVIE_A,
                media_type=WatchableMediaType.MOVIE,
                title="Inception",
                poster_path=f"/p/{_MOVIE_A}.jpg",
                backdrop_path=f"/b/{_MOVIE_A}.jpg",
                position_seconds=900,
                duration_seconds=3600,
                percentage=25.0,
                last_watched_at="2026-04-10T21:30:00+00:00",
            )
        ]

    @pytest.mark.asyncio
    async def test_completed_visible_movie_uses_a_slot_without_emitting(self, harness):
        for movie_id in (_MOVIE_A, _MOVIE_B, _MOVIE_C):
            harness.catalog.movies[movie_id] = _movie_info(movie_id)
        harness.single_page(
            [
                _movie_progress(_MOVIE_C, status="completed"),
                _movie_progress(_MOVIE_A),
                _movie_progress(_MOVIE_B),
            ]
        )

        result = await harness.use_case().execute(_input(limit=2))

        assert _ids(result.items) == [_MOVIE_A]
        display_call = harness.media_lookup.find_display_info.await_args
        assert display_call.kwargs["movie_ids"] == [MovieId(_MOVIE_A)]
        assert display_call.kwargs["series_ids"] == []


class TestSeriesDeduplication:
    """Tests for series deduplication and episode selection."""

    @pytest.mark.asyncio
    async def test_multiple_episodes_same_series_returns_one_item(self, harness):
        harness.catalog.series["ser_AAAAAAAAAAAA"] = _make_series_info(
            "ser_AAAAAAAAAAAA", {1: [1, 2, 3]}
        )

        p1 = _make_progress("epi_ser_AAAAAAAAAAAA_1_1")
        p2 = _make_progress("epi_ser_AAAAAAAAAAAA_1_2")
        p3 = _make_progress("epi_ser_AAAAAAAAAAAA_1_3")
        harness.single_page([p1, p2, p3])
        harness.uow.progress.find_by_media_ids.return_value = {
            "epi_ser_AAAAAAAAAAAA_1_1": p1,
            "epi_ser_AAAAAAAAAAAA_1_2": p2,
            "epi_ser_AAAAAAAAAAAA_1_3": p3,
        }

        result = await harness.use_case().execute(_input())

        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_picks_highest_in_progress_episode(self, harness):
        harness.catalog.series["ser_AAAAAAAAAAAA"] = _make_series_info(
            "ser_AAAAAAAAAAAA", {1: [1, 2, 3], 2: [1, 2]}
        )

        harness.single_page([_make_progress("epi_ser_AAAAAAAAAAAA_1_2")])
        harness.uow.progress.find_by_media_ids.return_value = {
            "epi_ser_AAAAAAAAAAAA_1_2": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_2",
                status="completed",
            ),
            "epi_ser_AAAAAAAAAAAA_1_3": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_3",
                status="in_progress",
            ),
            "epi_ser_AAAAAAAAAAAA_2_1": _make_progress(
                "epi_ser_AAAAAAAAAAAA_2_1",
                status="in_progress",
            ),
        }

        result = await harness.use_case().execute(_input())

        assert len(result.items) == 1
        assert result.items[0].season_number == 2
        assert result.items[0].episode_number == 1

    @pytest.mark.asyncio
    async def test_picks_next_unwatched_when_all_completed(self, harness):
        harness.catalog.series["ser_AAAAAAAAAAAA"] = _make_series_info(
            "ser_AAAAAAAAAAAA", {1: [1, 2, 3]}
        )

        harness.single_page([_make_progress("epi_ser_AAAAAAAAAAAA_1_1", status="completed")])
        harness.uow.progress.find_by_media_ids.return_value = {
            "epi_ser_AAAAAAAAAAAA_1_1": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_1",
                status="completed",
            ),
            "epi_ser_AAAAAAAAAAAA_1_2": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_2",
                status="completed",
            ),
        }

        result = await harness.use_case().execute(_input())

        assert len(result.items) == 1
        assert result.items[0].season_number == 1
        assert result.items[0].episode_number == 3
        assert result.items[0].percentage == 0.0

    @pytest.mark.asyncio
    async def test_returns_nothing_when_all_episodes_completed(self, harness):
        harness.catalog.series["ser_AAAAAAAAAAAA"] = _make_series_info(
            "ser_AAAAAAAAAAAA", {1: [1, 2]}
        )

        harness.single_page([_make_progress("epi_ser_AAAAAAAAAAAA_1_1", status="completed")])
        harness.uow.progress.find_by_media_ids.return_value = {
            "epi_ser_AAAAAAAAAAAA_1_1": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_1",
                status="completed",
            ),
            "epi_ser_AAAAAAAAAAAA_1_2": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_2",
                status="completed",
            ),
        }

        result = await harness.use_case().execute(_input())
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_two_series_return_one_item_each(self, harness):
        harness.catalog.series["ser_AAAAAAAAAAAA"] = _make_series_info(
            "ser_AAAAAAAAAAAA", {1: [1, 2]}, title="Series A"
        )
        harness.catalog.series["ser_BBBBBBBBBBBB"] = _make_series_info(
            "ser_BBBBBBBBBBBB", {1: [1]}, title="Series B"
        )

        pa = _make_progress("epi_ser_AAAAAAAAAAAA_1_1")
        pb = _make_progress("epi_ser_BBBBBBBBBBBB_1_1")
        harness.single_page([pa, pb])

        def find_by_media_ids_side_effect(ids, profile_id):
            id_values = [media_id.value for media_id in ids]
            result: dict[str, WatchProgress] = {}
            if "epi_ser_AAAAAAAAAAAA_1_1" in id_values:
                result["epi_ser_AAAAAAAAAAAA_1_1"] = pa
            if "epi_ser_BBBBBBBBBBBB_1_1" in id_values:
                result["epi_ser_BBBBBBBBBBBB_1_1"] = pb
            return result

        harness.uow.progress.find_by_media_ids.side_effect = find_by_media_ids_side_effect

        result = await harness.use_case().execute(_input())

        assert len(result.items) == 2
        series_ids = {item.series_id for item in result.items}
        assert series_ids == {"ser_AAAAAAAAAAAA", "ser_BBBBBBBBBBBB"}

    @pytest.mark.asyncio
    async def test_mixed_in_progress_and_completed_across_seasons(self, harness):
        harness.catalog.series["ser_AAAAAAAAAAAA"] = _make_series_info(
            "ser_AAAAAAAAAAAA", {1: [1, 2], 2: [1, 2]}
        )

        harness.single_page([_make_progress("epi_ser_AAAAAAAAAAAA_2_1")])
        harness.uow.progress.find_by_media_ids.return_value = {
            "epi_ser_AAAAAAAAAAAA_1_1": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_1",
                status="completed",
            ),
            "epi_ser_AAAAAAAAAAAA_1_2": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_2",
                status="completed",
            ),
            "epi_ser_AAAAAAAAAAAA_2_1": _make_progress(
                "epi_ser_AAAAAAAAAAAA_2_1",
                status="in_progress",
            ),
        }

        result = await harness.use_case().execute(_input())

        assert len(result.items) == 1
        assert result.items[0].season_number == 2
        assert result.items[0].episode_number == 1


class TestViewingPolicy:
    """Only titles the caller's profile can see reach the list."""

    @pytest.mark.asyncio
    async def test_deny_all_policy_returns_empty_without_reading(self):
        harness = _make_harness(ViewingPolicy(allowed_library_ids=[]))
        harness.catalog.movies[_MOVIE_A] = _movie_info(_MOVIE_A)
        harness.single_page([_movie_progress(_MOVIE_A)])

        result = await harness.use_case().execute(_input())

        assert result.items == []
        harness.uow.factory.assert_not_called()
        harness.uow.progress.list_recently_watched_page.assert_not_awaited()
        harness.media_lookup.find_visible_titles.assert_not_awaited()
        harness.media_lookup.find_display_info.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_policy_is_resolved_for_the_input_profile_before_any_uow(self, harness):
        harness.catalog.movies[_MOVIE_A] = _movie_info(_MOVIE_A)
        harness.single_page([_movie_progress(_MOVIE_A)])
        manager = Mock()
        manager.attach_mock(harness.policy_port.find_for_profile, "find_for_profile")
        manager.attach_mock(harness.uow.factory, "uow_factory")

        await harness.use_case().execute(_input())

        assert manager.mock_calls[0] == call.find_for_profile(_PROFILE_ID)
        assert call.uow_factory() in manager.mock_calls[1:]

    @pytest.mark.asyncio
    async def test_hidden_title_does_not_use_up_the_window(self, harness):
        for movie_id in (_MOVIE_A, _MOVIE_B, _MOVIE_HIDDEN):
            harness.catalog.movies[movie_id] = _movie_info(movie_id)
        harness.catalog.hidden.add(_MOVIE_HIDDEN)
        harness.single_page(
            [
                _movie_progress(_MOVIE_HIDDEN),
                _movie_progress(_MOVIE_A),
                _movie_progress(_MOVIE_B),
            ]
        )

        result = await harness.use_case().execute(_input(limit=2))

        assert _ids(result.items) == [_MOVIE_A, _MOVIE_B]
        assert _MOVIE_HIDDEN not in str(result)

    @pytest.mark.asyncio
    async def test_missing_and_hidden_titles_produce_the_same_list(self):
        """A small ``limit`` must not reveal whether the newest title exists."""

        async def run(first_row: str, *, exists: bool) -> list[ContinueWatchingItem]:
            harness = _make_harness()
            for movie_id in (_MOVIE_A, _MOVIE_B):
                harness.catalog.movies[movie_id] = _movie_info(movie_id)
            if exists:
                harness.catalog.movies[first_row] = _movie_info(first_row)
                harness.catalog.hidden.add(first_row)
            harness.single_page(
                [
                    _movie_progress(first_row),
                    _movie_progress(_MOVIE_A),
                    _movie_progress(_MOVIE_B),
                ]
            )
            return (await harness.use_case().execute(_input(limit=2))).items

        missing = await run(_MOVIE_MISSING, exists=False)
        hidden = await run(_MOVIE_MISSING, exists=True)

        assert missing == hidden
        assert _ids(missing) == [_MOVIE_A, _MOVIE_B]

    @pytest.mark.asyncio
    async def test_hidden_series_skips_every_episode_with_one_verdict(self, harness):
        hidden_series = "ser_HHHHHHHHHHHH"
        harness.catalog.series[hidden_series] = _make_series_info(hidden_series, {1: [1, 2, 3]})
        harness.catalog.hidden.add(hidden_series)
        harness.catalog.movies[_MOVIE_A] = _movie_info(_MOVIE_A)
        harness.stream(
            RecentlyWatchedPage(
                items=[
                    _make_progress(f"epi_{hidden_series}_1_3"),
                    _make_progress(f"epi_{hidden_series}_1_2"),
                ],
                next_cursor=_cursor(f"epi_{hidden_series}_1_2"),
            ),
            RecentlyWatchedPage(
                items=[
                    _make_progress(f"epi_{hidden_series}_1_1"),
                    _movie_progress(_MOVIE_A),
                ],
                next_cursor=None,
            ),
        )

        result = await harness.use_case().execute(_input(limit=2))

        assert _ids(result.items) == [_MOVIE_A]
        assert harness.media_lookup.find_visible_titles.await_args_list == [
            call(movie_ids=[], series_ids=[SeriesId(hidden_series)], policy=_POLICY),
            call(movie_ids=[MovieId(_MOVIE_A)], series_ids=[], policy=_POLICY),
        ]
        harness.uow.progress.find_by_media_ids.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_page_titles_are_judged_in_one_batched_call(self, harness):
        """One visibility lookup per page, never one per title (no N+1 on autosave-heavy streams)."""
        # The series is hidden so the assertion stays on the verdict lookup
        # alone; the mix of movies and a series is what the batch must cover.
        series = "ser_XXXXXXXXXXXX"
        harness.catalog.series[series] = _make_series_info(series, {1: [1, 2]})
        harness.catalog.hidden.add(series)
        for movie_id in (_MOVIE_A, _MOVIE_B):
            harness.catalog.movies[movie_id] = _movie_info(movie_id)
        harness.single_page(
            [
                _movie_progress(_MOVIE_A),
                _make_progress(f"epi_{series}_1_1"),
                _movie_progress(_MOVIE_B),
                _make_progress(f"epi_{series}_1_2"),
            ]
        )

        await harness.use_case().execute(_input(limit=5))

        assert harness.media_lookup.find_visible_titles.await_args_list == [
            call(
                movie_ids=[MovieId(_MOVIE_A), MovieId(_MOVIE_B)],
                series_ids=[SeriesId(series)],
                policy=_POLICY,
            ),
        ]

    @pytest.mark.asyncio
    async def test_display_info_gets_the_full_policy(self):
        limited = ViewingPolicy(allowed_library_ids=[_LIBRARY_ID], maturity_limit=AgeRating(12))
        harness = _make_harness(limited)
        harness.catalog.movies[_MOVIE_A] = _movie_info(_MOVIE_A)
        harness.single_page([_movie_progress(_MOVIE_A)])

        await harness.use_case().execute(_input())

        display_call = harness.media_lookup.find_display_info.await_args
        assert display_call.kwargs["policy"] == limited
        assert display_call.kwargs["policy"].maturity_limit == AgeRating(12)
        visible_call = harness.media_lookup.find_visible_titles.await_args
        assert visible_call.kwargs["policy"] == limited

    @pytest.mark.asyncio
    async def test_title_missing_from_display_is_dropped(self, harness):
        for movie_id in (_MOVIE_A, _MOVIE_B):
            harness.catalog.movies[movie_id] = _movie_info(movie_id)
        harness.catalog.series["ser_AAAAAAAAAAAA"] = _make_series_info("ser_AAAAAAAAAAAA", {1: [1]})
        harness.catalog.undisplayable.update({_MOVIE_A, "ser_AAAAAAAAAAAA"})
        harness.single_page(
            [
                _movie_progress(_MOVIE_A),
                _make_progress("epi_ser_AAAAAAAAAAAA_1_1"),
                _movie_progress(_MOVIE_B),
            ]
        )

        result = await harness.use_case().execute(_input())

        assert _ids(result.items) == [_MOVIE_B]


class TestWindowRefill:
    """The window is filled by keyset pages over the progress stream."""

    @pytest.mark.asyncio
    async def test_empty_page_with_cursor_reads_the_next_page(self, harness):
        harness.catalog.movies[_MOVIE_A] = _movie_info(_MOVIE_A)
        first_cursor = _cursor("epi_garbage")
        harness.stream(
            RecentlyWatchedPage(items=[], next_cursor=first_cursor),
            RecentlyWatchedPage(items=[_movie_progress(_MOVIE_A)], next_cursor=None),
        )

        result = await harness.use_case().execute(_input(limit=5))

        assert _ids(result.items) == [_MOVIE_A]
        page_calls = harness.uow.progress.list_recently_watched_page.await_args_list
        assert [c.kwargs["after"] for c in page_calls] == [None, first_cursor]

    @pytest.mark.asyncio
    async def test_hidden_rows_refill_from_the_next_page(self, harness):
        for movie_id in (_MOVIE_A, _MOVIE_HIDDEN):
            harness.catalog.movies[movie_id] = _movie_info(movie_id)
        harness.catalog.hidden.add(_MOVIE_HIDDEN)
        harness.stream(
            RecentlyWatchedPage(
                items=[_movie_progress(_MOVIE_HIDDEN)],
                next_cursor=_cursor(_MOVIE_HIDDEN),
            ),
            RecentlyWatchedPage(items=[_movie_progress(_MOVIE_A)], next_cursor=None),
        )

        result = await harness.use_case().execute(_input(limit=1))

        assert _ids(result.items) == [_MOVIE_A]

    @pytest.mark.asyncio
    async def test_exhausted_stream_stops_reading(self, harness):
        harness.catalog.movies[_MOVIE_A] = _movie_info(_MOVIE_A)
        # ``stream`` fails the test on a read past the last page.
        harness.single_page([_movie_progress(_MOVIE_A)])

        result = await harness.use_case().execute(_input(limit=5))

        assert _ids(result.items) == [_MOVIE_A]
        assert harness.uow.progress.list_recently_watched_page.await_count == 1

    @pytest.mark.asyncio
    async def test_full_window_stops_reading(self, harness):
        for movie_id in (_MOVIE_A, _MOVIE_B):
            harness.catalog.movies[movie_id] = _movie_info(movie_id)
        harness.stream(
            RecentlyWatchedPage(
                items=[_movie_progress(_MOVIE_A), _movie_progress(_MOVIE_B)],
                next_cursor=_cursor(_MOVIE_B),
            ),
        )

        result = await harness.use_case().execute(_input(limit=2))

        assert _ids(result.items) == [_MOVIE_A, _MOVIE_B]
        assert harness.uow.progress.list_recently_watched_page.await_count == 1

    @pytest.mark.asyncio
    async def test_row_repeated_across_pages_yields_one_item(self, harness):
        """A row read again because its stored key changed under the cursor counts once."""
        for movie_id in (_MOVIE_A, _MOVIE_B):
            harness.catalog.movies[movie_id] = _movie_info(movie_id)
        later = _BASE_TIME + timedelta(minutes=5)
        harness.stream(
            RecentlyWatchedPage(
                items=[_make_progress(_MOVIE_A, WatchableMediaType.MOVIE, last_watched=later)],
                next_cursor=RecentlyWatchedCursor(last_watched_at=later, media_id=_MOVIE_A),
            ),
            RecentlyWatchedPage(
                items=[_movie_progress(_MOVIE_A), _movie_progress(_MOVIE_B)],
                next_cursor=None,
            ),
        )

        result = await harness.use_case().execute(_input(limit=5))

        assert _ids(result.items) == [_MOVIE_A, _MOVIE_B]
