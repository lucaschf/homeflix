"""Tests for EnrichMovieMetadataUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaInput
from src.modules.media.application.ports import MediaMetadata, MetadataProvider
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository


def _make_movie() -> Movie:
    return Movie.create(
        title="Inception",
        year=2010,
        duration=0,
        file_path="/movies/inception.mkv",
        file_size=4_000_000_000,
        resolution="1080p",
    )


def _make_metadata() -> MediaMetadata:
    return MediaMetadata(
        title="Inception",
        original_title="Inception",
        year=2010,
        duration_seconds=8880,
        synopsis="A mind-bending thriller.",
        genres=["Sci-Fi", "Action"],
        tmdb_id=27205,
        imdb_id="tt1375666",
    )


@pytest.mark.unit
class TestEnrichMovieMetadata:
    """Tests for EnrichMovieMetadataUseCase."""

    @pytest.mark.asyncio
    async def test_should_enrich_movie_with_metadata(self) -> None:
        movie = _make_movie()
        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie
        repo.save.side_effect = lambda m: m

        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = _make_metadata()

        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is True
        assert result.provider == "tmdb"
        repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_skip_already_enriched_movie(self) -> None:
        movie = _make_movie()
        movie = movie.with_updates(tmdb_id=27205)

        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie

        provider = AsyncMock(spec=MetadataProvider)
        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)

        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is False
        provider.search_movie.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_force_re_enrich(self) -> None:
        movie = _make_movie()
        movie = movie.with_updates(tmdb_id=27205)

        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie
        repo.save.side_effect = lambda m: m

        provider = AsyncMock(spec=MetadataProvider)
        provider.get_movie_by_id.return_value = _make_metadata()

        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)

        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id), force=True))

        assert result.enriched is True

    @pytest.mark.asyncio
    async def test_should_use_fallback_when_primary_fails(self) -> None:
        movie = _make_movie()

        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie
        repo.save.side_effect = lambda m: m

        primary = AsyncMock(spec=MetadataProvider)
        primary.search_movie.return_value = None

        fallback = AsyncMock(spec=MetadataProvider)
        fallback.search_movie.return_value = _make_metadata()

        use_case = EnrichMovieMetadataUseCase(
            movie_repository=repo,
            primary_provider=primary,
            fallback_provider=fallback,
        )

        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is True
        assert result.provider == "omdb"

    @pytest.mark.asyncio
    async def test_should_return_error_when_no_metadata_found(self) -> None:
        movie = _make_movie()

        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie

        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = None

        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)

        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_should_raise_when_movie_not_found(self) -> None:
        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = None

        provider = AsyncMock(spec=MetadataProvider)
        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)

        from src.modules.media.domain.value_objects import MovieId

        fake_id = str(MovieId.generate())
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(EnrichMediaInput(media_id=fake_id))
