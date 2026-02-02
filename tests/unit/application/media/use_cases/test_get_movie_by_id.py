"""Tests for GetMovieByIdUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.application.media.dtos import GetMovieByIdInput, MovieOutput
from src.application.media.use_cases import GetMovieByIdUseCase
from src.application.shared.exceptions import ResourceNotFoundException
from src.domain.media.entities import Movie
from src.domain.media.repositories import MovieRepository


class TestGetMovieByIdUseCase:
    """Tests for GetMovieByIdUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_movie_when_found(self):
        mock_repo = AsyncMock(spec=MovieRepository)
        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        mock_repo.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(movie_repository=mock_repo)

        result = await use_case.execute(GetMovieByIdInput(movie_id=str(movie.id)))

        assert isinstance(result, MovieOutput)
        assert result.title == "Inception"
        assert result.year == 2010
        assert result.duration_seconds == 8880
        assert result.resolution == "1080p"

    @pytest.mark.asyncio
    async def test_should_return_formatted_duration(self):
        mock_repo = AsyncMock(spec=MovieRepository)
        movie = Movie.create(
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        mock_repo.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(movie_repository=mock_repo)

        result = await use_case.execute(GetMovieByIdInput(movie_id=str(movie.id)))

        assert result.duration_formatted == "02:00:00"

    @pytest.mark.asyncio
    async def test_should_return_genres_as_strings(self):
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
        movie.add_genre("Sci-Fi")
        mock_repo.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(movie_repository=mock_repo)

        result = await use_case.execute(GetMovieByIdInput(movie_id=str(movie.id)))

        assert result.genres == ["Action", "Sci-Fi"]

    @pytest.mark.asyncio
    async def test_should_handle_optional_fields_as_none(self):
        mock_repo = AsyncMock(spec=MovieRepository)
        movie = Movie.create(
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        mock_repo.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(movie_repository=mock_repo)

        result = await use_case.execute(GetMovieByIdInput(movie_id=str(movie.id)))

        assert result.original_title is None
        assert result.synopsis is None
        assert result.poster_path is None
        assert result.backdrop_path is None
        assert result.tmdb_id is None
        assert result.imdb_id is None

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_movie_missing(self):
        mock_repo = AsyncMock(spec=MovieRepository)
        mock_repo.find_by_id.return_value = None
        use_case = GetMovieByIdUseCase(movie_repository=mock_repo)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(GetMovieByIdInput(movie_id="mov_nonexistent1"))

        assert exc_info.value.resource_type == "Movie"
        assert exc_info.value.resource_id == "mov_nonexistent1"

    @pytest.mark.asyncio
    async def test_should_call_repository_with_movie_id(self):
        mock_repo = AsyncMock(spec=MovieRepository)
        movie = Movie.create(
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        mock_repo.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(movie_repository=mock_repo)

        await use_case.execute(GetMovieByIdInput(movie_id=str(movie.id)))

        mock_repo.find_by_id.assert_called_once()
        call_arg = mock_repo.find_by_id.call_args[0][0]
        assert str(call_arg) == str(movie.id)
