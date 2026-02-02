"""Tests for ListMoviesUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.application.media.dtos import ListMoviesInput, ListMoviesOutput, MovieSummaryOutput
from src.application.media.use_cases import ListMoviesUseCase
from src.domain.media.entities import Movie
from src.domain.media.repositories import MovieRepository


class TestListMoviesUseCase:
    """Tests for ListMoviesUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_all_movies(self):
        mock_repo = AsyncMock(spec=MovieRepository)
        movies = [
            Movie.create(
                title="Movie 1",
                year=2020,
                duration=7200,
                file_path="/movies/movie1.mkv",
                file_size=1_000_000_000,
                resolution="1080p",
            ),
            Movie.create(
                title="Movie 2",
                year=2021,
                duration=5400,
                file_path="/movies/movie2.mkv",
                file_size=2_000_000_000,
                resolution="4K",
            ),
        ]
        mock_repo.list_all.return_value = movies
        use_case = ListMoviesUseCase(movie_repository=mock_repo)

        result = await use_case.execute(ListMoviesInput())

        assert isinstance(result, ListMoviesOutput)
        assert len(result.movies) == 2
        assert result.total_count == 2

    @pytest.mark.asyncio
    async def test_should_return_movie_summaries(self):
        mock_repo = AsyncMock(spec=MovieRepository)
        movie = Movie.create(
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        movie.add_genre("Action")
        mock_repo.list_all.return_value = [movie]
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
    async def test_should_respect_limit_parameter(self):
        mock_repo = AsyncMock(spec=MovieRepository)
        movies = [
            Movie.create(
                title=f"Movie {i}",
                year=2020,
                duration=7200,
                file_path=f"/movies/movie{i}.mkv",
                file_size=1_000_000_000,
                resolution="1080p",
            )
            for i in range(5)
        ]
        mock_repo.list_all.return_value = movies
        use_case = ListMoviesUseCase(movie_repository=mock_repo)

        result = await use_case.execute(ListMoviesInput(limit=2))

        assert len(result.movies) == 2
        assert result.total_count == 5

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_movies(self):
        mock_repo = AsyncMock(spec=MovieRepository)
        mock_repo.list_all.return_value = []
        use_case = ListMoviesUseCase(movie_repository=mock_repo)

        result = await use_case.execute(ListMoviesInput())

        assert result.movies == []
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_should_handle_limit_greater_than_total(self):
        mock_repo = AsyncMock(spec=MovieRepository)
        movies = [
            Movie.create(
                title="Movie 1",
                year=2020,
                duration=7200,
                file_path="/movies/movie1.mkv",
                file_size=1_000_000_000,
                resolution="1080p",
            ),
        ]
        mock_repo.list_all.return_value = movies
        use_case = ListMoviesUseCase(movie_repository=mock_repo)

        result = await use_case.execute(ListMoviesInput(limit=100))

        assert len(result.movies) == 1
        assert result.total_count == 1
