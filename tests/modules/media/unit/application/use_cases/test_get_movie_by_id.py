"""Tests for GetMovieByIdUseCase."""


import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import GetMovieByIdInput, MovieOutput
from src.modules.media.application.use_cases import GetMovieByIdUseCase
from src.modules.media.domain.entities import Movie
from tests.modules.media.unit.conftest import (
    FakeProfileLibraryAccessPort,
    make_media_uow_mock,
    make_profile_library_access,
)

_LIBRARY_ID = "lib_test12345678"
_PROFILE_ID = "prf_test12345678"


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
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
        )

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
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
        )

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
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
        )

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
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id))
        )

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
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id="mov_nonexistent1")
            )

        assert exc_info.value.resource_type == "Movie"
        assert exc_info.value.resource_id == "mov_nonexistent1"

    @pytest.mark.asyncio
    async def test_should_call_repository_with_movie_id_and_allowed_libraries(self):
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
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        await use_case.execute(GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id=str(movie.id)))

        mocks.movies.find_by_id.assert_awaited_once()
        call_args = mocks.movies.find_by_id.await_args
        assert str(call_args.args[0]) == str(movie.id)
        assert list(call_args.kwargs["allowed_library_ids"]) == [_LIBRARY_ID]

    @pytest.mark.asyncio
    async def test_should_raise_404_for_deny_all_profile(self):
        # Deny-all profile must surface as 404 (matching the behavior
        # for a movie that lives outside the ACL — id-poking should
        # not leak the row's existence). Load-bearing security
        # assertion.
        mocks = make_media_uow_mock()
        use_case = GetMovieByIdUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: []}),
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetMovieByIdInput(profile_id=_PROFILE_ID, movie_id="mov_anything12345")
            )
        mocks.factory.assert_not_called()
        mocks.movies.find_by_id.assert_not_awaited()
