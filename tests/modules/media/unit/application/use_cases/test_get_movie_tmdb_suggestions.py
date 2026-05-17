"""Tests for GetMovieTmdbSuggestionsUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.admin_relink_dtos import (
    GetMovieTmdbSuggestionsInput,
)
from src.modules.media.application.ports import MetadataProvider, SearchCandidate
from src.modules.media.application.use_cases.get_movie_tmdb_suggestions import (
    GetMovieTmdbSuggestionsUseCase,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects import MovieId
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_movie(title: str = "Salem's Lot", year: int = 1979) -> Movie:
    return Movie.create(
        library_id=_LIBRARY_ID,
        title=title,
        year=year,
        duration=0,
        file_path="/movies/file.mkv",
        file_size=1,
        resolution="1080p",
    )


def _movie_candidate(tmdb_id: int, title: str, year: int | None = None) -> SearchCandidate:
    return SearchCandidate(
        tmdb_id=tmdb_id,
        media_type="movie",
        title=title,
        year=year,
        overview=None,
        poster_url=None,
    )


def _series_candidate(tmdb_id: int, title: str, year: int | None = None) -> SearchCandidate:
    return SearchCandidate(
        tmdb_id=tmdb_id,
        media_type="tv",
        title=title,
        year=year,
        overview=None,
        poster_url=None,
    )


@pytest.mark.unit
class TestGetMovieTmdbSuggestions:
    @pytest.mark.asyncio
    async def test_should_return_movie_and_series_candidates(self) -> None:
        movie = _make_movie()
        provider = AsyncMock(spec=MetadataProvider)
        provider.find_movie_candidates.return_value = [
            _movie_candidate(748230, "Salem's Lot", 2024),
        ]
        provider.find_series_candidates.return_value = [
            _series_candidate(16118, "Salem's Lot", 1979),
        ]
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = movie

        use_case = GetMovieTmdbSuggestionsUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
        )
        output = await use_case.execute(
            GetMovieTmdbSuggestionsInput(movie_id=str(movie.id)),
        )

        assert [c.tmdb_id for c in output.movies] == [748230]
        assert [c.tmdb_id for c in output.series] == [16118]
        assert output.movie_id == str(movie.id)

    @pytest.mark.asyncio
    async def test_should_retry_without_year_when_year_search_misses(self) -> None:
        """Picker mode prioritises showing *something* — when the
        year-hinted TMDB query is empty, retry without the year so
        the admin sees off-year candidates worth picking."""
        movie = _make_movie()
        provider = AsyncMock(spec=MetadataProvider)
        provider.find_movie_candidates.side_effect = [
            [],  # year=1979 returns nothing
            [_movie_candidate(748230, "Salem's Lot", 2024)],
        ]
        provider.find_series_candidates.return_value = []

        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = movie

        use_case = GetMovieTmdbSuggestionsUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
        )
        output = await use_case.execute(
            GetMovieTmdbSuggestionsInput(movie_id=str(movie.id)),
        )

        assert [c.tmdb_id for c in output.movies] == [748230]
        assert provider.find_movie_candidates.await_count == 2
        first_call, second_call = provider.find_movie_candidates.await_args_list
        assert first_call.args[1] == 1979
        assert second_call.args[1] is None

    @pytest.mark.asyncio
    async def test_should_raise_when_movie_not_found(self) -> None:
        provider = AsyncMock(spec=MetadataProvider)
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = None

        use_case = GetMovieTmdbSuggestionsUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetMovieTmdbSuggestionsInput(movie_id=str(MovieId.generate())),
            )
