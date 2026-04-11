"""Tests for EnrichMovieMetadataUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaInput
from src.modules.media.application.ports import (
    CreditPerson,
    LocalizedFields,
    MediaMetadata,
    MetadataProvider,
)
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
    _clean_title,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository
from src.modules.media.domain.value_objects import TmdbId


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
        movie = movie.with_updates(tmdb_id=TmdbId(27205))

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
        movie = movie.with_updates(tmdb_id=TmdbId(27205))

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

    @pytest.mark.asyncio
    async def test_should_use_localized_metadata_when_available(self) -> None:
        movie = _make_movie()
        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie
        repo.save.side_effect = lambda m: m

        # Provider with get_movie_localized method
        provider = MagicMock(spec=["search_movie", "get_movie_by_id", "get_movie_localized"])
        provider.search_movie = AsyncMock(return_value=_make_metadata())
        localized_meta = MediaMetadata(
            title="A Origem",
            tmdb_id=27205,
            localized={
                "pt-BR": LocalizedFields(title="A Origem", synopsis="Trama mental"),
            },
        )
        provider.get_movie_localized = AsyncMock(return_value=localized_meta)

        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is True
        provider.get_movie_localized.assert_awaited_once_with(27205)
        saved = repo.save.call_args[0][0]
        assert "pt-BR" in saved.localized

    @pytest.mark.asyncio
    async def test_should_retry_with_cleaned_title(self) -> None:
        movie = Movie.create(
            title="Inception 1080p BluRay x264",
            year=2010,
            duration=0,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie
        repo.save.side_effect = lambda m: m

        provider = AsyncMock(spec=MetadataProvider)

        # First call (with year): None. Second call (cleaned title): success
        provider.search_movie.side_effect = [None, _make_metadata()]

        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is True
        # Two attempts: with year, then cleaned
        assert provider.search_movie.await_count == 2

    @pytest.mark.asyncio
    async def test_should_retry_with_title_only_when_year_search_fails(self) -> None:
        movie = _make_movie()
        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie
        repo.save.side_effect = lambda m: m

        provider = AsyncMock(spec=MetadataProvider)
        # All searches return None except the title-only one
        provider.search_movie.side_effect = [None, _make_metadata()]

        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is True


@pytest.mark.unit
class TestCleanTitle:
    """Tests for the _clean_title helper."""

    def test_should_remove_resolution_tags(self) -> None:
        assert _clean_title("Inception 1080p").strip() == "Inception"

    def test_should_remove_codec_tags(self) -> None:
        assert _clean_title("Inception x264 AAC").strip() == "Inception"

    def test_should_remove_quality_tags(self) -> None:
        assert _clean_title("Inception BluRay HDR").strip() == "Inception"

    def test_should_remove_brackets(self) -> None:
        assert _clean_title("Inception [2010]").strip() == "Inception"

    def test_should_remove_parentheses(self) -> None:
        assert _clean_title("Inception (2010)").strip() == "Inception"

    def test_should_remove_audio_channels(self) -> None:
        assert _clean_title("Inception 5.1").strip() == "Inception"

    def test_should_remove_release_group_tags(self) -> None:
        assert _clean_title("Inception YIFY").strip() == "Inception"

    def test_should_preserve_clean_title(self) -> None:
        assert _clean_title("Inception").strip() == "Inception"


@pytest.mark.unit
class TestApplyMetadataFields:
    """Tests verifying _apply_movie_metadata applies all relevant fields."""

    @pytest.mark.asyncio
    async def test_should_apply_synopsis_when_missing(self) -> None:
        movie = _make_movie()
        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie
        repo.save.side_effect = lambda m: m
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = _make_metadata()

        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)
        await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        saved = repo.save.call_args[0][0]
        assert saved.synopsis == "A mind-bending thriller."

    @pytest.mark.asyncio
    async def test_should_apply_genres_when_missing(self) -> None:
        movie = _make_movie()
        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie
        repo.save.side_effect = lambda m: m
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = _make_metadata()

        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)
        await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        saved = repo.save.call_args[0][0]
        assert {g.value for g in saved.genres} == {"Sci-Fi", "Action"}

    @pytest.mark.asyncio
    async def test_should_apply_cast_directors_writers(self) -> None:
        movie = _make_movie()
        metadata = MediaMetadata(
            title="Inception",
            tmdb_id=27205,
            cast=[CreditPerson(name="Leonardo DiCaprio")],
            directors=[CreditPerson(name="Christopher Nolan")],
            writers=[CreditPerson(name="Christopher Nolan")],
            content_rating="PG-13",
            trailer_url="https://youtube.com/abc",
        )
        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie
        repo.save.side_effect = lambda m: m
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = metadata

        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)
        await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        saved = repo.save.call_args[0][0]
        assert saved.cast == ["Leonardo DiCaprio"]
        assert saved.directors == ["Christopher Nolan"]
        assert saved.writers == ["Christopher Nolan"]
        assert saved.content_rating == "PG-13"
        assert saved.trailer_url == "https://youtube.com/abc"

    @pytest.mark.asyncio
    async def test_should_apply_localized_fields(self) -> None:
        movie = _make_movie()
        metadata = MediaMetadata(
            title="Inception",
            tmdb_id=27205,
            localized={
                "pt-BR": LocalizedFields(
                    title="A Origem",
                    synopsis="Sonho dentro do sonho.",
                    genres=["Ficção Científica"],
                ),
            },
        )
        repo = AsyncMock(spec=MovieRepository)
        repo.find_by_id.return_value = movie
        repo.save.side_effect = lambda m: m
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = metadata

        use_case = EnrichMovieMetadataUseCase(movie_repository=repo, primary_provider=provider)
        await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        saved = repo.save.call_args[0][0]
        assert saved.localized["pt-BR"]["title"] == "A Origem"
        assert saved.localized["pt-BR"]["synopsis"] == "Sonho dentro do sonho."
        assert saved.localized["pt-BR"]["genres"] == ["Ficção Científica"]
