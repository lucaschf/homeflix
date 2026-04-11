"""Tests for ListMoviesUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.pagination import PaginatedResult, Pagination
from src.modules.media.application.dtos import ListMoviesInput, ListMoviesOutput, MovieSummaryOutput
from src.modules.media.application.use_cases import ListMoviesUseCase
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository


def _make_movie(title: str = "Test Movie", year: int = 2020) -> Movie:
    return Movie.create(
        title=title,
        year=year,
        duration=7200,
        file_path=f"/movies/{title.lower().replace(' ', '_')}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
    )


def _page(
    movies: list[Movie],
    *,
    next_cursor: str | None = None,
    has_more: bool = False,
    total_count: int | None = None,
) -> PaginatedResult[Movie]:
    return PaginatedResult(
        items=movies,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
        total_count=total_count,
    )


class TestListMoviesUseCase:
    """Tests for ListMoviesUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_first_page(self) -> None:
        mock_repo = AsyncMock(spec=MovieRepository)
        mock_repo.list_paginated.return_value = _page(
            [_make_movie("Movie 1"), _make_movie("Movie 2")],
            has_more=False,
        )
        use_case = ListMoviesUseCase(movie_repository=mock_repo)

        result = await use_case.execute(ListMoviesInput())

        assert isinstance(result, ListMoviesOutput)
        assert len(result.movies) == 2
        assert result.has_more is False
        assert result.next_cursor is None
        # include_total defaults to False → repo gets include_total=False → total_count is None
        assert result.total_count is None
        mock_repo.list_paginated.assert_awaited_once_with(
            cursor=None,
            limit=20,
            include_total=False,
        )

    @pytest.mark.asyncio
    async def test_should_convert_movies_to_summaries(self) -> None:
        mock_repo = AsyncMock(spec=MovieRepository)
        movie = _make_movie("Test Movie", 2020).with_genre("Action")
        mock_repo.list_paginated.return_value = _page([movie])
        use_case = ListMoviesUseCase(movie_repository=mock_repo)

        result = await use_case.execute(ListMoviesInput())

        summary = result.movies[0]
        assert isinstance(summary, MovieSummaryOutput)
        assert summary.title == "Test Movie"
        assert summary.year == 2020
        assert summary.duration_formatted == "02:00:00"
        assert summary.resolution == "1080p"
        assert summary.genres == ["Action"]

    @pytest.mark.asyncio
    async def test_should_pass_cursor_and_limit_to_repository(self) -> None:
        mock_repo = AsyncMock(spec=MovieRepository)
        mock_repo.list_paginated.return_value = _page([])
        use_case = ListMoviesUseCase(movie_repository=mock_repo)

        await use_case.execute(ListMoviesInput(cursor="abc123", limit=15))

        mock_repo.list_paginated.assert_awaited_once_with(
            cursor="abc123",
            limit=15,
            include_total=False,
        )

    @pytest.mark.asyncio
    async def test_should_propagate_next_cursor_and_has_more(self) -> None:
        mock_repo = AsyncMock(spec=MovieRepository)
        mock_repo.list_paginated.return_value = _page(
            [_make_movie("Movie 1")],
            next_cursor="next-token",
            has_more=True,
        )
        use_case = ListMoviesUseCase(movie_repository=mock_repo)

        result = await use_case.execute(ListMoviesInput())

        assert result.next_cursor == "next-token"
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_should_return_empty_page_when_no_movies(self) -> None:
        mock_repo = AsyncMock(spec=MovieRepository)
        mock_repo.list_paginated.return_value = _page([])
        use_case = ListMoviesUseCase(movie_repository=mock_repo)

        result = await use_case.execute(ListMoviesInput())

        assert result.movies == []
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_should_request_total_when_include_total_is_true(self) -> None:
        mock_repo = AsyncMock(spec=MovieRepository)
        mock_repo.list_paginated.return_value = _page(
            [_make_movie("Movie 1")],
            total_count=42,
        )
        use_case = ListMoviesUseCase(movie_repository=mock_repo)

        result = await use_case.execute(ListMoviesInput(include_total=True))

        assert result.total_count == 42
        mock_repo.list_paginated.assert_awaited_once_with(
            cursor=None,
            limit=20,
            include_total=True,
        )
