"""Tests for ListByGenreUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.pagination import (
    PaginatedResult,
    Pagination,
    decode_dual_cursor,
)
from src.modules.media.application.dtos.catalog_dtos import (
    CatalogItemOutput,
    ListByGenreInput,
    ListByGenreOutput,
)
from src.modules.media.application.use_cases.list_by_genre import ListByGenreUseCase
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository


def _movie(title: str) -> Movie:
    return Movie.create(
        title=title,
        year=2020,
        duration=7200,
        file_path=f"/movies/{title.lower().replace(' ', '_')}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
    )


def _series(title: str) -> Series:
    return Series.create(title=title, start_year=2020)


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


@pytest.mark.unit
class TestListByGenreUseCase:
    """Merge + dual-cursor behavior of ListByGenreUseCase."""

    @pytest.mark.asyncio
    async def test_should_merge_movies_and_series_alphabetically(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        movie_repo.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Avatar"), _movie("Cyrano")]
        )
        series_repo.list_paginated_by_genre.return_value = _series_page([_series("Breaking Bad")])
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        result = await use_case.execute(ListByGenreInput(genre="Action"))

        assert isinstance(result, ListByGenreOutput)
        titles = [item.title for item in result.items]
        # Sorted by lowercase title
        assert titles == ["Avatar", "Breaking Bad", "Cyrano"]

    @pytest.mark.asyncio
    async def test_should_tag_each_item_with_its_type(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        movie_repo.list_paginated_by_genre.return_value = _movies_page([_movie("Avatar")])
        series_repo.list_paginated_by_genre.return_value = _series_page([_series("Breaking Bad")])
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        result = await use_case.execute(ListByGenreInput(genre="Action"))

        types = {(item.title, item.type) for item in result.items}
        assert types == {("Avatar", "movie"), ("Breaking Bad", "series")}

    @pytest.mark.asyncio
    async def test_should_pass_decoded_cursors_to_each_repo(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        movie_repo.list_paginated_by_genre.return_value = _movies_page([])
        series_repo.list_paginated_by_genre.return_value = _series_page([])
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        # Build a real dual cursor so the use case decodes it
        from src.building_blocks.application.pagination import encode_dual_cursor

        cursor = encode_dual_cursor("movies-token", "series-token")
        await use_case.execute(ListByGenreInput(genre="Action", cursor=cursor))

        movie_call_kwargs = movie_repo.list_paginated_by_genre.await_args.kwargs
        series_call_kwargs = series_repo.list_paginated_by_genre.await_args.kwargs
        assert movie_call_kwargs["cursor"] == "movies-token"
        assert series_call_kwargs["cursor"] == "series-token"

    @pytest.mark.asyncio
    async def test_should_advance_cursor_only_for_consumed_streams(self) -> None:
        # Movies stream wins the merge entirely (all titles are
        # alphabetically before any series). The series cursor must
        # stay at its previous value so the next page re-considers
        # the same starting series.
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        movie_repo.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Apple"), _movie("Banana")],
            has_more=True,
        )
        # Series with title "Zebra" — sorts AFTER both movies, so it
        # won't fit in a 2-item page.
        series_repo.list_paginated_by_genre.return_value = _series_page(
            [_series("Zebra")],
            has_more=False,
        )
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        from src.building_blocks.application.pagination import encode_dual_cursor

        previous_cursor = encode_dual_cursor(None, "previous-series-cursor")
        result = await use_case.execute(
            ListByGenreInput(genre="Action", cursor=previous_cursor, limit=2)
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
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        # Each repo returns 3 items, total 6 — limit 2 means 4 are
        # left over and `has_more` must be true even if neither
        # individual repo says so.
        movie_repo.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Apple"), _movie("Cherry"), _movie("Eggplant")],
            has_more=False,
        )
        series_repo.list_paginated_by_genre.return_value = _series_page(
            [_series("Banana"), _series("Date"), _series("Fig")],
            has_more=False,
        )
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        result = await use_case.execute(ListByGenreInput(genre="Action", limit=2))

        assert len(result.items) == 2
        assert [item.title for item in result.items] == ["Apple", "Banana"]
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_should_return_no_cursor_when_both_streams_exhausted(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        movie_repo.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Avatar")], has_more=False
        )
        series_repo.list_paginated_by_genre.return_value = _series_page(
            [_series("Breaking Bad")], has_more=False
        )
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        result = await use_case.execute(ListByGenreInput(genre="Action", limit=10))

        assert len(result.items) == 2
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_should_return_empty_when_no_items_match(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        movie_repo.list_paginated_by_genre.return_value = _movies_page([])
        series_repo.list_paginated_by_genre.return_value = _series_page([])
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        result = await use_case.execute(ListByGenreInput(genre="NoSuchGenre"))

        assert result.items == []
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_should_skip_series_repo_when_filtered_to_movies(self) -> None:
        # media_type="movie" restricts the merge to the movie stream
        # — series repo stays silent so the output is a pure movies
        # listing for the Movies tab.
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        movie_repo.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Avatar"), _movie("Cyrano")]
        )
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        result = await use_case.execute(ListByGenreInput(genre="Action", media_type="movie"))

        movie_repo.list_paginated_by_genre.assert_awaited_once()
        series_repo.list_paginated_by_genre.assert_not_awaited()
        assert [item.type for item in result.items] == ["movie", "movie"]
        assert [item.title for item in result.items] == ["Avatar", "Cyrano"]

    @pytest.mark.asyncio
    async def test_should_skip_movie_repo_when_filtered_to_series(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        series_repo.list_paginated_by_genre.return_value = _series_page(
            [_series("Breaking Bad"), _series("Dark")]
        )
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        result = await use_case.execute(ListByGenreInput(genre="Action", media_type="series"))

        series_repo.list_paginated_by_genre.assert_awaited_once()
        movie_repo.list_paginated_by_genre.assert_not_awaited()
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
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        movie_repo.list_paginated_by_genre.return_value = _movies_page(
            [_movie("Apple"), _movie("Banana")],
            has_more=True,
        )
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        from src.building_blocks.application.pagination import encode_dual_cursor

        previous_cursor = encode_dual_cursor(None, "untouched-series-cursor")
        result = await use_case.execute(
            ListByGenreInput(
                genre="Action",
                cursor=previous_cursor,
                limit=2,
                media_type="movie",
            )
        )

        assert result.has_more is True
        decoded = decode_dual_cursor(result.next_cursor)
        assert decoded.movies == "m-cursor-1"
        assert decoded.series == "untouched-series-cursor"

    @pytest.mark.asyncio
    async def test_catalog_item_output_carries_required_fields(self) -> None:
        movie_repo = AsyncMock(spec=MovieRepository)
        series_repo = AsyncMock(spec=SeriesRepository)
        movie_repo.list_paginated_by_genre.return_value = _movies_page([_movie("Test")])
        series_repo.list_paginated_by_genre.return_value = _series_page([])
        use_case = ListByGenreUseCase(movie_repo, series_repo)

        result = await use_case.execute(ListByGenreInput(genre="Action"))

        item = result.items[0]
        assert isinstance(item, CatalogItemOutput)
        assert item.title == "Test"
        assert item.type == "movie"
        assert item.year == 2020
