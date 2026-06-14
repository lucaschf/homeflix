"""Tests for FlagMovieEnrichmentReviewUseCase."""

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.admin_relink_dtos import (
    FlagMovieEnrichmentReviewInput,
)
from src.modules.media.application.use_cases.flag_movie_enrichment_review import (
    FlagMovieEnrichmentReviewUseCase,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects import MovieId
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_movie() -> Movie:
    return Movie.create(
        library_id=_LIBRARY_ID,
        title="Salem's Lot",
        year=1979,
        duration=0,
        file_path="/movies/file.mkv",
        file_size=1,
        resolution="1080p",
    )


@pytest.mark.unit
class TestFlagMovieEnrichmentReview:
    @pytest.mark.asyncio
    async def test_should_flag_and_persist_movie(self) -> None:
        movie = _make_movie()
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = movie
        mocks.movies.save.side_effect = lambda m: m

        use_case = FlagMovieEnrichmentReviewUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            FlagMovieEnrichmentReviewInput(movie_id=str(movie.id)),
        )

        assert result.movie_id == str(movie.id)
        assert result.needs_enrichment_review is True

        mocks.movies.save.assert_called_once()
        saved = mocks.movies.save.call_args.args[0]
        assert saved.needs_enrichment_review is True

    @pytest.mark.asyncio
    async def test_should_not_persist_when_already_flagged(self) -> None:
        """Idempotent: re-flagging an already-flagged movie must not
        write (avoids a spurious ``updated_at`` bump)."""
        movie = _make_movie().with_enrichment_review_flagged()
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = movie

        use_case = FlagMovieEnrichmentReviewUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            FlagMovieEnrichmentReviewInput(movie_id=str(movie.id)),
        )

        assert result.needs_enrichment_review is True
        mocks.movies.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_raise_when_movie_not_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = None

        use_case = FlagMovieEnrichmentReviewUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                FlagMovieEnrichmentReviewInput(movie_id=str(MovieId.generate())),
            )
