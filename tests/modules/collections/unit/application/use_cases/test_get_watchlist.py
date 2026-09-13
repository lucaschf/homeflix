"""Tests for GetWatchlistUseCase."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, call

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    MOVIES_LIBRARY_ID,
    SERIES_LIBRARY_ID,
    make_media_lookup_mock,
    make_profile_viewing_policy_mock,
    make_progress_lookup_mock,
)
from tests.modules.collections.unit.conftest import (
    CollectionsUoWMocks,
    make_collections_uow_mock,
)

from src.modules.collections.application.dtos import (
    GetWatchlistInput,
    WatchlistItemOutput,
)
from src.modules.collections.application.ports import MediaLookupPort
from src.modules.collections.application.use_cases import GetWatchlistUseCase
from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.repositories import WatchlistCursor, WatchlistPage
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.media_id import MovieId
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from tests.modules.collections.unit.application.use_cases.conftest import (
        MediaSummaryFactory,
    )

_PROFILE_ID = ProfileId("prf_test12345678")
_OTHER_LIBRARY_ID = "lib_otherlib0001"

_MOVIE_A = "mov_aaaaaaaaaaaa"
_MOVIE_B = "mov_bbbbbbbbbbbb"
_MOVIE_C = "mov_cccccccccccc"
_MOVIE_HIDDEN = "mov_hhhhhhhhhhhh"
_MOVIE_MISSING = "mov_xxxxxxxxxxxx"
_ADDED_AT = datetime(2026, 9, 13, tzinfo=UTC)

_LOGGER = "src.modules.collections.application.use_cases.get_watchlist"


def _item(media_id: str) -> WatchlistItem:
    media_type = MediaType.MOVIE if media_id.startswith("mov_") else MediaType.SERIES
    return WatchlistItem.create(profile_id=_PROFILE_ID, media_id=media_id, media_type=media_type)


def _cursor(media_id: str) -> WatchlistCursor:
    return WatchlistCursor(added_at=_ADDED_AT, media_id=media_id)


def _stream(mocks: CollectionsUoWMocks, *pages: WatchlistPage) -> None:
    """Serve these pages in order; reading past the last one fails the test."""
    remaining = list(pages)

    async def next_page(
        profile_id: ProfileId,
        *,
        limit: int,
        after: WatchlistCursor | None,
    ) -> WatchlistPage:
        if not remaining:
            raise AssertionError("read past the end of the watchlist")
        return remaining.pop(0)

    mocks.watchlist.list_page.side_effect = next_page


def _single_page(mocks: CollectionsUoWMocks, items: list[WatchlistItem]) -> None:
    _stream(mocks, WatchlistPage(items=items, next_cursor=None))


def _use_case(
    mocks: CollectionsUoWMocks,
    media_lookup: AsyncMock,
    *,
    progress_lookup: AsyncMock | None = None,
    policy_port: AsyncMock | None = None,
) -> GetWatchlistUseCase:
    return GetWatchlistUseCase(
        uow_factory=mocks.factory,
        media_lookup=media_lookup,
        progress_lookup=progress_lookup or make_progress_lookup_mock(),
        profile_viewing_policy=policy_port
        or make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID, SERIES_LIBRARY_ID),
    )


def _input(*, limit: int = 100, lang: str = "en") -> GetWatchlistInput:
    return GetWatchlistInput(profile_id=_PROFILE_ID.value, limit=limit, lang=lang)


def _ids(result: list[WatchlistItemOutput]) -> list[str]:
    return [item.media_id for item in result]


@pytest.mark.unit
class TestGetWatchlistUseCase:
    """Tests for getting watchlist items with metadata."""

    @pytest.mark.asyncio
    async def test_should_return_items_with_metadata(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item("mov_abc123def456")])

        media_lookup = make_media_lookup_mock(
            movie_summary("mov_abc123def456", "Inception"),
        )

        result = await _use_case(mocks, media_lookup).execute(_input())

        assert len(result) == 1
        assert isinstance(result[0], WatchlistItemOutput)
        assert result[0].title == "Inception"

    @pytest.mark.asyncio
    async def test_should_carry_enrichment_fields_from_summary(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item("mov_abc123def456")])
        media_lookup = make_media_lookup_mock(movie_summary("mov_abc123def456"))

        out = (await _use_case(mocks, media_lookup).execute(_input()))[0]

        assert out.year == 2010
        assert out.runtime_seconds == 8880
        assert out.genres == ("Action", "Sci-Fi")
        assert out.resolution == "4K"
        assert out.hdr is True

    @pytest.mark.asyncio
    async def test_should_attach_progress_for_movies(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item("mov_abc123def456")])

        use_case = _use_case(
            mocks,
            make_media_lookup_mock(movie_summary("mov_abc123def456")),
            progress_lookup=make_progress_lookup_mock({"mov_abc123def456": 0.42}),
        )

        out = (await use_case.execute(_input()))[0]

        assert out.progress == 0.42

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_items(self) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [])
        media_lookup = AsyncMock(spec=MediaLookupPort)

        result = await _use_case(mocks, media_lookup).execute(_input())

        assert result == []
        media_lookup.get_many.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_skip_missing_media(self) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item("mov_missing00000")])

        result = await _use_case(mocks, make_media_lookup_mock()).execute(_input())

        assert result == []

    @pytest.mark.asyncio
    async def test_should_handle_mixed_media_types(
        self,
        movie_summary: MediaSummaryFactory,
        series_summary: MediaSummaryFactory,
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item("mov_abc123def456"), _item("ser_xyz789abc123")])

        media_lookup = make_media_lookup_mock(
            movie_summary("mov_abc123def456", "Inception"),
            series_summary("ser_xyz789abc123", "Breaking Bad"),
        )

        result = await _use_case(mocks, media_lookup).execute(_input())

        assert len(result) == 2
        assert result[0].title == "Inception"
        assert result[1].title == "Breaking Bad"

    @pytest.mark.asyncio
    async def test_should_respect_limit(self) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [])

        await _use_case(mocks, AsyncMock(spec=MediaLookupPort)).execute(_input(limit=25))

        mocks.watchlist.list_page.assert_awaited_once_with(_PROFILE_ID, limit=100, after=None)

    @pytest.mark.asyncio
    async def test_should_pass_language_to_media_lookup(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item("mov_abc123def456")])

        media_lookup = make_media_lookup_mock(movie_summary("mov_abc123def456"))

        await _use_case(mocks, media_lookup).execute(_input(lang="pt-BR"))

        media_lookup.get_many.assert_awaited_once_with(
            [MovieId("mov_abc123def456")],
            [],
            "pt-BR",
        )


@pytest.mark.unit
class TestGetWatchlistViewingPolicy:
    """Only titles the caller's profile can see are listed, without using up ``limit``."""

    @pytest.mark.asyncio
    async def test_deny_all_policy_returns_empty_without_reading(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item(_MOVIE_A)])
        media_lookup = make_media_lookup_mock(movie_summary(_MOVIE_A))
        progress_lookup = make_progress_lookup_mock()

        result = await _use_case(
            mocks,
            media_lookup,
            progress_lookup=progress_lookup,
            policy_port=make_profile_viewing_policy_mock(),
        ).execute(_input())

        assert result == []
        mocks.factory.assert_not_called()
        mocks.watchlist.list_page.assert_not_awaited()
        media_lookup.get_many.assert_not_awaited()
        progress_lookup.get_progress.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_policy_is_resolved_for_the_input_profile_before_any_uow(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item(_MOVIE_A)])
        policy_port = make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID)
        manager = Mock()
        manager.attach_mock(policy_port.find_for_profile, "find_for_profile")
        manager.attach_mock(mocks.factory, "uow_factory")

        await _use_case(
            mocks, make_media_lookup_mock(movie_summary(_MOVIE_A)), policy_port=policy_port
        ).execute(_input())

        assert manager.mock_calls[0] == call.find_for_profile(_PROFILE_ID)
        assert call.uow_factory() in manager.mock_calls[1:]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("library_id", "minimum_age"),
        [
            pytest.param(MOVIES_LIBRARY_ID, AgeRating(16), id="above-limit"),
            pytest.param(MOVIES_LIBRARY_ID, None, id="unrated-under-limit"),
            pytest.param(_OTHER_LIBRARY_ID, AgeRating(10), id="other-library"),
        ],
    )
    async def test_denied_title_does_not_use_up_the_limit(
        self,
        movie_summary: MediaSummaryFactory,
        library_id: str,
        minimum_age: AgeRating | None,
    ) -> None:
        mocks = make_collections_uow_mock()
        _stream(
            mocks,
            WatchlistPage(
                items=[_item(_MOVIE_HIDDEN), _item(_MOVIE_A)], next_cursor=_cursor(_MOVIE_A)
            ),
            WatchlistPage(items=[_item(_MOVIE_B)], next_cursor=None),
        )
        media_lookup = make_media_lookup_mock(
            movie_summary(_MOVIE_HIDDEN, "Hidden", library_id=library_id, minimum_age=minimum_age),
            movie_summary(_MOVIE_A, minimum_age=AgeRating(10)),
            movie_summary(_MOVIE_B, minimum_age=AgeRating(10)),
        )

        result = await _use_case(
            mocks,
            media_lookup,
            policy_port=make_profile_viewing_policy_mock(
                MOVIES_LIBRARY_ID, maturity_limit=AgeRating(12)
            ),
        ).execute(_input(limit=2))

        assert _ids(result) == [_MOVIE_A, _MOVIE_B]
        assert "Hidden" not in str(result)
        page_calls = mocks.watchlist.list_page.await_args_list
        assert [c.kwargs["after"] for c in page_calls] == [None, _cursor(_MOVIE_A)]
        assert {c.kwargs["limit"] for c in page_calls} == {100}

    @pytest.mark.asyncio
    async def test_missing_media_does_not_use_up_the_limit_and_is_logged(
        self, movie_summary: MediaSummaryFactory, caplog: pytest.LogCaptureFixture
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item(_MOVIE_MISSING), _item(_MOVIE_A), _item(_MOVIE_B)])
        media_lookup = make_media_lookup_mock(movie_summary(_MOVIE_A), movie_summary(_MOVIE_B))

        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            result = await _use_case(mocks, media_lookup).execute(_input(limit=2))

        assert _ids(result) == [_MOVIE_A, _MOVIE_B]
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert _MOVIE_MISSING in warnings[0].getMessage()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("library_id", "minimum_age"),
        [
            pytest.param(MOVIES_LIBRARY_ID, AgeRating(16), id="above-limit"),
            pytest.param(_OTHER_LIBRARY_ID, AgeRating(10), id="other-library"),
        ],
    )
    async def test_denied_title_is_dropped_without_a_warning(
        self,
        movie_summary: MediaSummaryFactory,
        caplog: pytest.LogCaptureFixture,
        library_id: str,
        minimum_age: AgeRating | None,
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item(_MOVIE_HIDDEN), _item(_MOVIE_A)])
        media_lookup = make_media_lookup_mock(
            movie_summary(_MOVIE_HIDDEN, library_id=library_id, minimum_age=minimum_age),
            movie_summary(_MOVIE_A, minimum_age=AgeRating(10)),
        )

        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            result = await _use_case(
                mocks,
                media_lookup,
                policy_port=make_profile_viewing_policy_mock(
                    MOVIES_LIBRARY_ID, maturity_limit=AgeRating(12)
                ),
            ).execute(_input())

        assert _ids(result) == [_MOVIE_A]
        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []

    @pytest.mark.asyncio
    async def test_missing_and_denied_titles_produce_the_same_list(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        """A small ``limit`` must not reveal whether the newest title exists."""

        rows = [_item(_MOVIE_HIDDEN), _item(_MOVIE_A)]

        async def run(*, exists: bool) -> list[WatchlistItemOutput]:
            mocks = make_collections_uow_mock()
            _single_page(mocks, rows)
            summaries = [movie_summary(_MOVIE_A, minimum_age=AgeRating(10))]
            if exists:
                summaries.append(movie_summary(_MOVIE_HIDDEN, minimum_age=AgeRating(16)))
            return await _use_case(
                mocks,
                make_media_lookup_mock(*summaries),
                policy_port=make_profile_viewing_policy_mock(
                    MOVIES_LIBRARY_ID, maturity_limit=AgeRating(12)
                ),
            ).execute(_input(limit=1))

        missing = await run(exists=False)
        hidden = await run(exists=True)

        assert missing == hidden
        assert _ids(missing) == [_MOVIE_A]

    @pytest.mark.asyncio
    async def test_unrated_and_all_ages_titles_under_limits(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        """``AgeRating(0)`` is a real rating; ``None`` reads as adult."""
        free = "mov_livre0000001"
        unrated = "mov_unrated00001"

        async def run(limit: int) -> list[str]:
            mocks = make_collections_uow_mock()
            _single_page(mocks, [_item(free), _item(unrated)])
            return _ids(
                await _use_case(
                    mocks,
                    make_media_lookup_mock(
                        movie_summary(free, minimum_age=AgeRating(0)),
                        movie_summary(unrated, minimum_age=None),
                    ),
                    policy_port=make_profile_viewing_policy_mock(
                        MOVIES_LIBRARY_ID, maturity_limit=AgeRating(limit)
                    ),
                ).execute(_input())
            )

        assert await run(12) == [free]
        assert await run(18) == [free, unrated]


@pytest.mark.unit
class TestGetWatchlistRefill:
    """The list is filled by keyset pages over the watchlist."""

    @pytest.mark.asyncio
    async def test_exhausted_watchlist_stops_reading(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        mocks = make_collections_uow_mock()
        # ``_stream`` fails the test on a read past the last page.
        _single_page(mocks, [_item(_MOVIE_A)])

        result = await _use_case(mocks, make_media_lookup_mock(movie_summary(_MOVIE_A))).execute(
            _input(limit=5)
        )

        assert _ids(result) == [_MOVIE_A]
        assert mocks.watchlist.list_page.await_count == 1

    @pytest.mark.asyncio
    async def test_full_list_stops_reading(self, movie_summary: MediaSummaryFactory) -> None:
        mocks = make_collections_uow_mock()
        _stream(
            mocks,
            WatchlistPage(items=[_item(_MOVIE_A), _item(_MOVIE_B)], next_cursor=_cursor(_MOVIE_B)),
        )
        media_lookup = make_media_lookup_mock(movie_summary(_MOVIE_A), movie_summary(_MOVIE_B))

        result = await _use_case(mocks, media_lookup).execute(_input(limit=2))

        assert _ids(result) == [_MOVIE_A, _MOVIE_B]
        assert mocks.watchlist.list_page.await_count == 1

    @pytest.mark.asyncio
    async def test_list_filled_mid_page_stops_taking_items(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        mocks = make_collections_uow_mock()
        _stream(
            mocks,
            WatchlistPage(
                items=[_item(_MOVIE_HIDDEN), _item(_MOVIE_A)], next_cursor=_cursor(_MOVIE_A)
            ),
            WatchlistPage(items=[_item(_MOVIE_B), _item(_MOVIE_C)], next_cursor=_cursor(_MOVIE_C)),
        )
        media_lookup = make_media_lookup_mock(
            movie_summary(_MOVIE_HIDDEN, library_id=_OTHER_LIBRARY_ID),
            movie_summary(_MOVIE_A),
            movie_summary(_MOVIE_B),
            movie_summary(_MOVIE_C),
        )
        progress_lookup = make_progress_lookup_mock()

        result = await _use_case(mocks, media_lookup, progress_lookup=progress_lookup).execute(
            _input(limit=2)
        )

        assert _ids(result) == [_MOVIE_A, _MOVIE_B]
        progress_lookup.get_progress.assert_awaited_once_with(
            [_MOVIE_A, _MOVIE_B], profile_id=_PROFILE_ID.value
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("limit", "page_rows"),
        [pytest.param(1, 100, id="small-limit"), pytest.param(500, 500, id="large-limit")],
    )
    async def test_pages_are_never_narrower_than_page_rows(
        self, limit: int, page_rows: int
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [])

        await _use_case(mocks, AsyncMock(spec=MediaLookupPort)).execute(_input(limit=limit))

        mocks.watchlist.list_page.assert_awaited_once_with(_PROFILE_ID, limit=page_rows, after=None)

    @pytest.mark.asyncio
    async def test_cursor_that_does_not_advance_stops_reading(
        self, movie_summary: MediaSummaryFactory, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A hidden row that sorts below its own cursor must not be read forever."""

        def stuck_page() -> WatchlistPage:
            return WatchlistPage(items=[_item(_MOVIE_HIDDEN)], next_cursor=_cursor(_MOVIE_HIDDEN))

        mocks = make_collections_uow_mock()
        # ``_stream`` fails the test on a third read instead of hanging.
        _stream(mocks, stuck_page(), stuck_page())
        media_lookup = make_media_lookup_mock(
            movie_summary(_MOVIE_HIDDEN, library_id=_OTHER_LIBRARY_ID)
        )

        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            result = await _use_case(mocks, media_lookup).execute(_input(limit=1))

        assert result == []
        assert mocks.watchlist.list_page.await_count == 2
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert _PROFILE_ID.value in warnings[0].getMessage()

    @pytest.mark.asyncio
    async def test_item_repeated_across_pages_yields_one_item(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        mocks = make_collections_uow_mock()
        _stream(
            mocks,
            WatchlistPage(items=[_item(_MOVIE_A)], next_cursor=_cursor(_MOVIE_A)),
            WatchlistPage(items=[_item(_MOVIE_A), _item(_MOVIE_B)], next_cursor=None),
        )
        media_lookup = make_media_lookup_mock(movie_summary(_MOVIE_A), movie_summary(_MOVIE_B))

        result = await _use_case(mocks, media_lookup).execute(_input(limit=5))

        assert _ids(result) == [_MOVIE_A, _MOVIE_B]
        assert [c.args[0] for c in media_lookup.get_many.await_args_list] == [
            [MovieId(_MOVIE_A)],
            [MovieId(_MOVIE_B)],
        ]

    @pytest.mark.asyncio
    async def test_progress_is_looked_up_only_for_listed_movies(
        self,
        movie_summary: MediaSummaryFactory,
        series_summary: MediaSummaryFactory,
    ) -> None:
        mocks = make_collections_uow_mock()
        series_id = "ser_xyz789abc123"
        _single_page(
            mocks,
            [_item(_MOVIE_HIDDEN), _item(_MOVIE_MISSING), _item(_MOVIE_A), _item(series_id)],
        )
        media_lookup = make_media_lookup_mock(
            movie_summary(_MOVIE_HIDDEN, library_id=_OTHER_LIBRARY_ID),
            movie_summary(_MOVIE_A),
            series_summary(series_id),
        )
        progress_lookup = make_progress_lookup_mock({_MOVIE_A: 0.5})

        result = await _use_case(mocks, media_lookup, progress_lookup=progress_lookup).execute(
            _input()
        )

        assert _ids(result) == [_MOVIE_A, series_id]
        progress_lookup.get_progress.assert_awaited_once_with(
            [_MOVIE_A], profile_id=_PROFILE_ID.value
        )

    @pytest.mark.asyncio
    async def test_nothing_listed_skips_the_progress_lookup(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        mocks = make_collections_uow_mock()
        _single_page(mocks, [_item(_MOVIE_HIDDEN)])
        progress_lookup = make_progress_lookup_mock()

        result = await _use_case(
            mocks,
            make_media_lookup_mock(movie_summary(_MOVIE_HIDDEN, library_id=_OTHER_LIBRARY_ID)),
            progress_lookup=progress_lookup,
        ).execute(_input())

        assert result == []
        progress_lookup.get_progress.assert_not_awaited()
