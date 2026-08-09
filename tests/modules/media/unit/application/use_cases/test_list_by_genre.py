"""Tests for ListByGenreUseCase."""

from datetime import UTC, datetime
from typing import Any

import pytest

from src.building_blocks.application.pagination import decode_dual_cursor
from src.building_blocks.domain.pagination import PaginatedResult, Pagination
from src.modules.media.application.dtos.catalog_dtos import (
    CatalogItemOutput,
    ListByGenreInput,
    ListByGenreOutput,
)
from src.modules.media.application.use_cases.list_by_genre import ListByGenreUseCase
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.value_objects import CatalogSort
from src.shared_kernel.value_objects import MediaType
from tests.modules.media.unit.conftest import (
    FakeProfileLibraryAccessPort,
    make_media_uow_mock,
)

_LIBRARY_ID = "lib_test12345678"
_LIBRARY_ID_OTHER = "lib_otherlibrary"
_PROFILE_ID = "prf_test12345678"


def _movie(
    title: str,
    *,
    year: int = 2020,
    created_at: datetime | None = None,
    library_id: str = _LIBRARY_ID,
) -> Movie:
    kwargs: dict[str, Any] = {}
    if created_at is not None:
        kwargs["created_at"] = created_at
    return Movie.create(
        library_id=library_id,
        title=title,
        year=year,
        duration=7200,
        file_path=f"/movies/{title.lower().replace(' ', '_')}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
        **kwargs,
    )


def _series(
    title: str,
    *,
    start_year: int = 2020,
    created_at: datetime | None = None,
    library_id: str = _LIBRARY_ID,
) -> Series:
    kwargs: dict[str, Any] = {}
    if created_at is not None:
        kwargs["created_at"] = created_at
    return Series.create(library_id=library_id, title=title, start_year=start_year, **kwargs)


def _movies_page(
    movies: list[Movie],
    *,
    has_more: bool = False,
    next_cursor: str | None = None,
) -> PaginatedResult[Movie]:
    cursors = [f"m-cursor-{i}" for i in range(len(movies))]
    return PaginatedResult(
        items=movies,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
        item_cursors=cursors,
    )


def _series_page(
    series_list: list[Series],
    *,
    has_more: bool = False,
    next_cursor: str | None = None,
) -> PaginatedResult[Series]:
    cursors = [f"s-cursor-{i}" for i in range(len(series_list))]
    return PaginatedResult(
        items=series_list,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
        item_cursors=cursors,
    )


def _make_use_case(mocks, *, allowed: list[str] | None = None) -> ListByGenreUseCase:
    if allowed is None:
        allowed = [_LIBRARY_ID]
    return ListByGenreUseCase(
        uow_factory=mocks.factory,
        profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: allowed}),
    )


@pytest.mark.unit
class TestListByGenreUseCase:
    """Merge + dual-cursor behavior of ListByGenreUseCase."""

    @pytest.mark.asyncio
    async def test_should_merge_movies_and_series_alphabetically(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Avatar"), _movie("Cyrano")]
        )
        mocks.series.list_paginated_by_genre.return_value = _series_page([_series("Breaking Bad")])
        use_case = _make_use_case(mocks)

        result = await use_case.execute(ListByGenreInput(profile_id=_PROFILE_ID, genre="Action"))

        assert isinstance(result, ListByGenreOutput)
        titles = [item.title for item in result.items]
        # Sorted by lowercase title
        assert titles == ["Avatar", "Breaking Bad", "Cyrano"]

    @pytest.mark.asyncio
    async def test_should_tag_each_item_with_its_type(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page([_movie("Avatar")])
        mocks.series.list_paginated_by_genre.return_value = _series_page([_series("Breaking Bad")])
        use_case = _make_use_case(mocks)

        result = await use_case.execute(ListByGenreInput(profile_id=_PROFILE_ID, genre="Action"))

        types = {(item.title, item.type) for item in result.items}
        assert types == {("Avatar", "movie"), ("Breaking Bad", "series")}

    @pytest.mark.asyncio
    async def test_should_pass_decoded_cursors_to_each_repo(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page([])
        mocks.series.list_paginated_by_genre.return_value = _series_page([])
        use_case = _make_use_case(mocks)

        # Build a real dual cursor so the use case decodes it
        from src.building_blocks.application.pagination import encode_dual_cursor

        cursor = encode_dual_cursor("movies-token", "series-token")
        await use_case.execute(
            ListByGenreInput(profile_id=_PROFILE_ID, genre="Action", cursor=cursor)
        )

        movie_call_kwargs = mocks.movies.list_paginated_by_genre.await_args.kwargs
        series_call_kwargs = mocks.series.list_paginated_by_genre.await_args.kwargs
        assert movie_call_kwargs["cursor"] == "movies-token"
        assert series_call_kwargs["cursor"] == "series-token"
        assert list(movie_call_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
        assert list(series_call_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]

    @pytest.mark.asyncio
    async def test_should_advance_cursor_only_for_consumed_streams(self) -> None:
        # Movies stream wins the merge entirely (all titles are
        # alphabetically before any series). The series cursor must
        # stay at its previous value so the next page re-considers
        # the same starting series.
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Apple"), _movie("Banana")],
            has_more=True,
        )
        # Series with title "Zebra" — sorts AFTER both movies, so it
        # won't fit in a 2-item page.
        mocks.series.list_paginated_by_genre.return_value = _series_page(
            [_series("Zebra")],
            has_more=False,
        )
        use_case = _make_use_case(mocks)

        from src.building_blocks.application.pagination import encode_dual_cursor

        previous_cursor = encode_dual_cursor(None, "previous-series-cursor")
        result = await use_case.execute(
            ListByGenreInput(
                profile_id=_PROFILE_ID,
                genre="Action",
                cursor=previous_cursor,
                limit=2,
            )
        )

        assert result.has_more is True
        decoded = decode_dual_cursor(result.next_cursor)
        # Movies advanced to the cursor of the LAST consumed movie
        # (Banana, index 1 in its page).
        assert decoded.movies == "m-cursor-1"
        # Series did not advance — keeps the previous cursor unchanged
        # so the next page re-considers Zebra.
        assert decoded.series == "previous-series-cursor"

    @pytest.mark.asyncio
    async def test_should_truncate_to_requested_limit_and_set_has_more(
        self,
    ) -> None:
        mocks = make_media_uow_mock()
        # Each repo returns 3 items, total 6 — limit 2 means 4 are
        # left over and `has_more` must be true even if neither
        # individual repo says so.
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Apple"), _movie("Cherry"), _movie("Eggplant")],
            has_more=False,
        )
        mocks.series.list_paginated_by_genre.return_value = _series_page(
            [_series("Banana"), _series("Date"), _series("Fig")],
            has_more=False,
        )
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ListByGenreInput(profile_id=_PROFILE_ID, genre="Action", limit=2)
        )

        assert len(result.items) == 2
        assert [item.title for item in result.items] == ["Apple", "Banana"]
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_should_return_no_cursor_when_both_streams_exhausted(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Avatar")], has_more=False
        )
        mocks.series.list_paginated_by_genre.return_value = _series_page(
            [_series("Breaking Bad")], has_more=False
        )
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ListByGenreInput(profile_id=_PROFILE_ID, genre="Action", limit=10)
        )

        assert len(result.items) == 2
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_should_return_empty_when_no_items_match(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page([])
        mocks.series.list_paginated_by_genre.return_value = _series_page([])
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ListByGenreInput(profile_id=_PROFILE_ID, genre="NoSuchGenre")
        )

        assert result.items == []
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_should_skip_series_repo_when_filtered_to_movies(self) -> None:
        # media_type=MediaType.MOVIE restricts the merge to the movie stream
        # — series repo stays silent so the output is a pure movies
        # listing for the Movies tab.
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Avatar"), _movie("Cyrano")]
        )
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ListByGenreInput(profile_id=_PROFILE_ID, genre="Action", media_type=MediaType.MOVIE)
        )

        mocks.movies.list_paginated_by_genre.assert_awaited_once()
        mocks.series.list_paginated_by_genre.assert_not_awaited()
        assert [item.type for item in result.items] == ["movie", "movie"]
        assert [item.title for item in result.items] == ["Avatar", "Cyrano"]

    @pytest.mark.asyncio
    async def test_should_skip_movie_repo_when_filtered_to_series(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_paginated_by_genre.return_value = _series_page(
            [_series("Breaking Bad"), _series("Dark")]
        )
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ListByGenreInput(profile_id=_PROFILE_ID, genre="Action", media_type=MediaType.SERIES)
        )

        mocks.series.list_paginated_by_genre.assert_awaited_once()
        mocks.movies.list_paginated_by_genre.assert_not_awaited()
        assert [item.type for item in result.items] == ["series", "series"]
        assert [item.title for item in result.items] == ["Breaking Bad", "Dark"]

    @pytest.mark.asyncio
    async def test_should_advance_only_filtered_stream_cursor_when_filtered(
        self,
    ) -> None:
        # Under a media-type filter only the surviving stream's
        # cursor should advance — the skipped stream's slot in the
        # dual cursor must round-trip unchanged so a later unfiltered
        # request doesn't have to start from scratch.
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Apple"), _movie("Banana")],
            has_more=True,
        )
        use_case = _make_use_case(mocks)

        from src.building_blocks.application.pagination import encode_dual_cursor

        previous_cursor = encode_dual_cursor(None, "untouched-series-cursor")
        result = await use_case.execute(
            ListByGenreInput(
                profile_id=_PROFILE_ID,
                genre="Action",
                cursor=previous_cursor,
                limit=2,
                media_type=MediaType.MOVIE,
            )
        )

        assert result.has_more is True
        decoded = decode_dual_cursor(result.next_cursor)
        assert decoded.movies == "m-cursor-1"
        assert decoded.series == "untouched-series-cursor"

    @pytest.mark.asyncio
    async def test_catalog_item_output_carries_required_fields(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page([_movie("Test")])
        mocks.series.list_paginated_by_genre.return_value = _series_page([])
        use_case = _make_use_case(mocks)

        result = await use_case.execute(ListByGenreInput(profile_id=_PROFILE_ID, genre="Action"))

        item = result.items[0]
        assert isinstance(item, CatalogItemOutput)
        assert item.title == "Test"
        assert item.type == "movie"
        assert item.year == 2020

    @pytest.mark.asyncio
    async def test_should_short_circuit_for_deny_all_profile(self) -> None:
        mocks = make_media_uow_mock()
        use_case = ListByGenreUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: []}),
        )

        result = await use_case.execute(ListByGenreInput(profile_id=_PROFILE_ID, genre="Action"))

        assert result.items == []
        assert result.has_more is False
        assert result.next_cursor is None
        mocks.factory.assert_not_called()
        mocks.movies.list_paginated_by_genre.assert_not_awaited()
        mocks.series.list_paginated_by_genre.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_forward_only_allowed_libraries_for_inclusion_path(
        self,
    ) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page([_movie("Visible")])
        mocks.series.list_paginated_by_genre.return_value = _series_page([])
        use_case = _make_use_case(mocks)

        result = await use_case.execute(ListByGenreInput(profile_id=_PROFILE_ID, genre="Action"))

        assert [item.title for item in result.items] == ["Visible"]
        movie_kwargs = mocks.movies.list_paginated_by_genre.await_args.kwargs
        series_kwargs = mocks.series.list_paginated_by_genre.await_args.kwargs
        assert list(movie_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
        assert list(series_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
        assert _LIBRARY_ID_OTHER not in list(movie_kwargs["allowed_library_ids"])


@pytest.mark.unit
class TestListByGenreSort:
    """The merge respects the requested ``sort`` across both streams."""

    @pytest.mark.asyncio
    async def test_should_default_to_title_ascending(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Avatar"), _movie("Cyrano")]
        )
        mocks.series.list_paginated_by_genre.return_value = _series_page([_series("Breaking Bad")])
        use_case = _make_use_case(mocks)

        result = await use_case.execute(ListByGenreInput(profile_id=_PROFILE_ID, genre="Action"))

        assert [item.title for item in result.items] == ["Avatar", "Breaking Bad", "Cyrano"]
        # The default input forwards TITLE_ASC to both repositories.
        assert (
            mocks.movies.list_paginated_by_genre.await_args.kwargs["sort"] is CatalogSort.TITLE_ASC
        )

    @pytest.mark.asyncio
    async def test_should_sort_by_title_descending(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Avatar"), _movie("Cyrano")]
        )
        mocks.series.list_paginated_by_genre.return_value = _series_page([_series("Breaking Bad")])
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ListByGenreInput(profile_id=_PROFILE_ID, genre="Action", sort=CatalogSort.TITLE_DESC)
        )

        assert [item.title for item in result.items] == ["Cyrano", "Breaking Bad", "Avatar"]

    @pytest.mark.asyncio
    async def test_should_sort_by_year_descending(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Old", year=2000), _movie("Mid", year=2010)]
        )
        mocks.series.list_paginated_by_genre.return_value = _series_page(
            [_series("New", start_year=2020)]
        )
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ListByGenreInput(profile_id=_PROFILE_ID, genre="Action", sort=CatalogSort.YEAR_DESC)
        )

        assert [item.title for item in result.items] == ["New", "Mid", "Old"]
        assert [item.year for item in result.items] == [2020, 2010, 2000]

    @pytest.mark.asyncio
    async def test_should_sort_by_year_ascending(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Old", year=2000), _movie("Mid", year=2010)]
        )
        mocks.series.list_paginated_by_genre.return_value = _series_page(
            [_series("New", start_year=2020)]
        )
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ListByGenreInput(profile_id=_PROFILE_ID, genre="Action", sort=CatalogSort.YEAR_ASC)
        )

        assert [item.year for item in result.items] == [2000, 2010, 2020]

    @pytest.mark.asyncio
    async def test_should_sort_by_recently_added_using_created_at(self) -> None:
        # Cross-stream "newest first" orders by created_at (movie ids and
        # series ids come from independent sequences and aren't
        # comparable), matching ListRecentlyAddedCatalogUseCase.
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [
                _movie("Newest", created_at=datetime(2024, 1, 3, tzinfo=UTC)),
                _movie("Oldest", created_at=datetime(2024, 1, 1, tzinfo=UTC)),
            ]
        )
        mocks.series.list_paginated_by_genre.return_value = _series_page(
            [_series("Middle", created_at=datetime(2024, 1, 2, tzinfo=UTC))]
        )
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ListByGenreInput(
                profile_id=_PROFILE_ID, genre="Action", sort=CatalogSort.RECENTLY_ADDED
            )
        )

        assert [item.title for item in result.items] == ["Newest", "Middle", "Oldest"]

    @pytest.mark.asyncio
    async def test_should_forward_sort_to_both_repositories(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page([])
        mocks.series.list_paginated_by_genre.return_value = _series_page([])
        use_case = _make_use_case(mocks)

        await use_case.execute(
            ListByGenreInput(profile_id=_PROFILE_ID, genre="Action", sort=CatalogSort.YEAR_DESC)
        )

        assert (
            mocks.movies.list_paginated_by_genre.await_args.kwargs["sort"] is CatalogSort.YEAR_DESC
        )
        assert (
            mocks.series.list_paginated_by_genre.await_args.kwargs["sort"] is CatalogSort.YEAR_DESC
        )

    @pytest.mark.asyncio
    async def test_should_break_year_ties_by_source_order_within_a_stream(self) -> None:
        # Two movies share a year: the merge must keep them in the
        # stream's own (year, id) order — a descending primary must not
        # flip the source-order tie-break — and the consumed-aware
        # cursor must advance to the last consumed row.
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated_by_genre.return_value = _movies_page(
            [_movie("A", year=2010), _movie("B", year=2010)],
            has_more=True,
        )
        mocks.series.list_paginated_by_genre.return_value = _series_page([])
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            ListByGenreInput(
                profile_id=_PROFILE_ID, genre="Action", limit=1, sort=CatalogSort.YEAR_ASC
            )
        )

        assert [item.title for item in result.items] == ["A"]
        assert result.has_more is True
        decoded = decode_dual_cursor(result.next_cursor)
        assert decoded.movies == "m-cursor-0"
