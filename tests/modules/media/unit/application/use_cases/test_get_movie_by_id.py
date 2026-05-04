"""Tests for GetMovieByIdUseCase."""


import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import GetMovieByIdInput, MovieOutput
from src.modules.media.application.use_cases import GetMovieByIdUseCase
from src.modules.media.domain.entities import Movie
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


class TestGetMovieByIdUseCase:
    """Tests for GetMovieByIdUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_movie_when_found(self):
        mocks = make_media_uow_mock()
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        mocks.movies.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(GetMovieByIdInput(movie_id=str(movie.id)))

        assert isinstance(result, MovieOutput)
        assert result.title == "Inception"
        assert result.year == 2010
        assert result.duration_seconds == 8880
        assert result.resolution == "1080p"

    @pytest.mark.asyncio
    async def test_should_return_formatted_duration(self):
        mocks = make_media_uow_mock()
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        mocks.movies.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(GetMovieByIdInput(movie_id=str(movie.id)))

        assert result.duration_formatted == "02:00:00"

    @pytest.mark.asyncio
    async def test_should_return_genres_as_strings(self):
        mocks = make_media_uow_mock()
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        movie = movie.with_genre("Action")
        movie = movie.with_genre("Sci-Fi")
        mocks.movies.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(GetMovieByIdInput(movie_id=str(movie.id)))

        assert result.genres == ["Action", "Sci-Fi"]

    @pytest.mark.asyncio
    async def test_should_handle_optional_fields_as_none(self):
        mocks = make_media_uow_mock()
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        mocks.movies.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(GetMovieByIdInput(movie_id=str(movie.id)))

        assert result.original_title is None
        assert result.synopsis is None
        assert result.poster_path is None
        assert result.backdrop_path is None
        assert result.tmdb_id is None
        assert result.imdb_id is None

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_movie_missing(self):
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = None
        use_case = GetMovieByIdUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(GetMovieByIdInput(movie_id="mov_nonexistent1"))

        assert exc_info.value.resource_type == "Movie"
        assert exc_info.value.resource_id == "mov_nonexistent1"

    @pytest.mark.asyncio
    async def test_should_call_repository_with_movie_id(self):
        mocks = make_media_uow_mock()
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Test Movie",
            year=2020,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )
        mocks.movies.find_by_id.return_value = movie
        use_case = GetMovieByIdUseCase(uow_factory=mocks.factory)

        await use_case.execute(GetMovieByIdInput(movie_id=str(movie.id)))

        mocks.movies.find_by_id.assert_called_once()
        call_arg = mocks.movies.find_by_id.call_args[0][0]
        assert str(call_arg) == str(movie.id)
