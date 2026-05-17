"""Tests for ListMoviesNeedingReviewUseCase."""

import pytest

from src.modules.media.application.use_cases.list_movies_needing_review import (
    ListMoviesNeedingReviewUseCase,
)
from src.modules.media.domain.entities import Movie
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_movie(title: str, year: int, file_path: str | None = "/movies/file.mkv") -> Movie:
    return Movie.create(
        library_id=_LIBRARY_ID,
        title=title,
        year=year,
        duration=0,
        file_path=file_path or "/dev/null",
        file_size=1,
        resolution="1080p",
    )


@pytest.mark.unit
class TestListMoviesNeedingReview:
    @pytest.mark.asyncio
    async def test_should_return_flagged_movies(self) -> None:
        flagged = [
            _make_movie("Salem's Lot", 1979),
            _make_movie("American Gothic", 2016),
        ]
        mocks = make_media_uow_mock()
        mocks.movies.find_needs_enrichment_review.return_value = flagged

        use_case = ListMoviesNeedingReviewUseCase(uow_factory=mocks.factory)
        output = await use_case.execute()

        assert len(output.movies) == 2
        assert {m.title for m in output.movies} == {"Salem's Lot", "American Gothic"}
        assert all(m.id.startswith("mov_") for m in output.movies)

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_none_flagged(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_needs_enrichment_review.return_value = []

        use_case = ListMoviesNeedingReviewUseCase(uow_factory=mocks.factory)
        output = await use_case.execute()

        assert output.movies == []

    @pytest.mark.asyncio
    async def test_should_surface_primary_file_path(self) -> None:
        """File path is the most actionable hint for an admin scrolling
        a list of un-enriched titles — make sure the projection keeps it."""
        movie = _make_movie("Salem's Lot", 1979, file_path="/movies/Salem (1979).mkv")
        mocks = make_media_uow_mock()
        mocks.movies.find_needs_enrichment_review.return_value = [movie]

        use_case = ListMoviesNeedingReviewUseCase(uow_factory=mocks.factory)
        output = await use_case.execute()

        assert output.movies[0].file_path == "/movies/Salem (1979).mkv"
