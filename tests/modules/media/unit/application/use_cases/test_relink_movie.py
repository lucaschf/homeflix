"""Tests for RelinkMovieUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.modules.media.application.dtos.admin_relink_dtos import RelinkMovieInput
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaOutput
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.application.use_cases.relink_movie import RelinkMovieUseCase
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
class TestRelinkMovie:
    @pytest.mark.asyncio
    async def test_should_stamp_tmdb_id_and_force_enrich_on_movie_pick(self) -> None:
        movie = _make_movie()
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = movie
        mocks.movies.save.side_effect = lambda m: m

        enrich = AsyncMock(spec=EnrichMovieMetadataUseCase)
        enrich.execute.return_value = EnrichMediaOutput(
            media_id=str(movie.id),
            enriched=True,
            provider="tmdb",
        )

        use_case = RelinkMovieUseCase(uow_factory=mocks.factory, enrich_use_case=enrich)
        result = await use_case.execute(
            RelinkMovieInput(movie_id=str(movie.id), tmdb_id=12345, media_type="movie"),
        )

        assert result.enriched is True
        assert result.provider == "tmdb"

        # The pre-enrich save stamped the picked TMDB id.
        mocks.movies.save.assert_called_once()
        saved = mocks.movies.save.call_args.args[0]
        assert saved.tmdb_id is not None
        assert saved.tmdb_id.value == 12345

        # Enrich was triggered with force=True so the new id wins
        # even though the row had no tmdb_id before.
        enrich.execute.assert_awaited_once()
        enrich_input = enrich.execute.await_args.args[0]
        assert enrich_input.media_id == str(movie.id)
        assert enrich_input.force is True

    @pytest.mark.asyncio
    async def test_should_reject_tv_media_type_with_validation_error(self) -> None:
        """Cross-type relink (Movie → Series) is deferred to a future
        promote-to-series flow; the endpoint must surface the limitation
        instead of silently succeeding."""
        mocks = make_media_uow_mock()
        enrich = AsyncMock(spec=EnrichMovieMetadataUseCase)

        use_case = RelinkMovieUseCase(uow_factory=mocks.factory, enrich_use_case=enrich)

        with pytest.raises(UseCaseValidationException) as excinfo:
            await use_case.execute(
                RelinkMovieInput(
                    movie_id=str(MovieId.generate()),
                    tmdb_id=16118,
                    media_type="tv",
                ),
            )

        assert excinfo.value.message_code == "RELINK_CROSS_TYPE_NOT_SUPPORTED"
        mocks.movies.find_by_id.assert_not_called()
        enrich.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_raise_when_movie_not_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = None
        enrich = AsyncMock(spec=EnrichMovieMetadataUseCase)

        use_case = RelinkMovieUseCase(uow_factory=mocks.factory, enrich_use_case=enrich)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                RelinkMovieInput(
                    movie_id=str(MovieId.generate()),
                    tmdb_id=12345,
                    media_type="movie",
                ),
            )
