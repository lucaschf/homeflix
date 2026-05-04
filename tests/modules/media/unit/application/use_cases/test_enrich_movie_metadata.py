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
from src.modules.media.domain.value_objects import ContentRating, TmdbId
from src.modules.media.domain.value_objects.cast_member import CastMember
from tests.modules.media.unit.conftest import MediaUoWMocks, make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_movie() -> Movie:
    return Movie.create(
        library_id=_LIBRARY_ID,
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


def _set_up_enrichment(
    movie: Movie, provider: MetadataProvider
) -> tuple[EnrichMovieMetadataUseCase, MediaUoWMocks]:
    mocks = make_media_uow_mock()
    mocks.movies.find_by_id.return_value = movie
    mocks.movies.save.side_effect = lambda m: m
    use_case = EnrichMovieMetadataUseCase(uow_factory=mocks.factory, primary_provider=provider)
    return use_case, mocks


@pytest.mark.unit
class TestEnrichMovieMetadata:
    """Tests for EnrichMovieMetadataUseCase."""

    @pytest.mark.asyncio
    async def test_should_enrich_movie_with_metadata(self) -> None:
        movie = _make_movie()
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = _make_metadata()

        use_case, mocks = _set_up_enrichment(movie, provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is True
        assert result.provider == "tmdb"
        mocks.movies.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_skip_already_enriched_movie(self) -> None:
        movie = _make_movie().with_updates(tmdb_id=TmdbId(27205))
        provider = AsyncMock(spec=MetadataProvider)

        use_case, _ = _set_up_enrichment(movie, provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is False
        provider.search_movie.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_force_re_enrich(self) -> None:
        movie = _make_movie().with_updates(tmdb_id=TmdbId(27205))
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_movie_by_id.return_value = _make_metadata()

        use_case, _ = _set_up_enrichment(movie, provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id), force=True))

        assert result.enriched is True

    @pytest.mark.asyncio
    async def test_should_use_fallback_when_primary_fails(self) -> None:
        movie = _make_movie()
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = movie
        mocks.movies.save.side_effect = lambda m: m

        primary = AsyncMock(spec=MetadataProvider)
        primary.search_movie.return_value = None

        fallback = AsyncMock(spec=MetadataProvider)
        fallback.search_movie.return_value = _make_metadata()

        use_case = EnrichMovieMetadataUseCase(
            uow_factory=mocks.factory,
            primary_provider=primary,
            fallback_provider=fallback,
        )

        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is True
        assert result.provider == "omdb"

    @pytest.mark.asyncio
    async def test_should_return_error_when_no_metadata_found(self) -> None:
        movie = _make_movie()
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = None

        use_case, _ = _set_up_enrichment(movie, provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_should_raise_when_movie_not_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = None

        provider = AsyncMock(spec=MetadataProvider)
        use_case = EnrichMovieMetadataUseCase(uow_factory=mocks.factory, primary_provider=provider)

        from src.modules.media.domain.value_objects import MovieId

        fake_id = str(MovieId.generate())
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(EnrichMediaInput(media_id=fake_id))

    @pytest.mark.asyncio
    async def test_should_use_localized_metadata_when_available(self) -> None:
        movie = _make_movie()
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = movie
        mocks.movies.save.side_effect = lambda m: m

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

        use_case = EnrichMovieMetadataUseCase(uow_factory=mocks.factory, primary_provider=provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is True
        provider.get_movie_localized.assert_awaited_once_with(27205)
        saved = mocks.movies.save.call_args[0][0]
        assert "pt-BR" in saved.localized

    @pytest.mark.asyncio
    async def test_should_retry_with_cleaned_title(self) -> None:
        movie = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception 1080p BluRay x264",
            year=2010,
            duration=0,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.side_effect = [None, _make_metadata()]

        use_case, _ = _set_up_enrichment(movie, provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is True
        assert provider.search_movie.await_count == 2

    @pytest.mark.asyncio
    async def test_should_retry_with_title_only_when_year_search_fails(self) -> None:
        movie = _make_movie()
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.side_effect = [None, _make_metadata()]

        use_case, _ = _set_up_enrichment(movie, provider)
        result = await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        assert result.enriched is True


@pytest.mark.unit
class TestEnrichMovieMetadataForce:
    """``force=True`` must bypass the ``not movie.<field>`` guards.

    Motivating use case: backfill ``tmdb_id`` on cast members of
    movies enriched before the id was captured. Without the force
    bypass on ``_apply_credits`` the cast field stays untouched and
    the actor page never gets bio links.
    """

    @pytest.mark.asyncio
    async def test_should_overwrite_existing_cast_with_tmdb_id(self) -> None:
        # Old enrichment shape: cast present but ``tmdb_id`` is None
        # because the row was saved before we captured the id.
        movie = _make_movie().with_updates(
            tmdb_id=TmdbId(27205),
            cast=[CastMember(name="Leonardo DiCaprio", tmdb_id=None)],
        )
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_movie_by_id.return_value = MediaMetadata(
            title="Inception",
            tmdb_id=27205,
            cast=[
                CreditPerson(
                    name="Leonardo DiCaprio",
                    role="Cobb",
                    profile_url="https://image.tmdb.org/t/p/original/leo.jpg",
                    tmdb_id=6193,
                ),
            ],
        )

        captured: dict[str, Movie] = {}

        async def _capture(m: Movie) -> Movie:
            captured["saved"] = m
            return m

        use_case, mocks = _set_up_enrichment(movie, provider)
        mocks.movies.save.side_effect = _capture

        result = await use_case.execute(
            EnrichMediaInput(media_id=str(movie.id), force=True),
        )

        assert result.enriched is True
        saved = captured["saved"]
        assert len(saved.cast) == 1
        assert saved.cast[0].name == "Leonardo DiCaprio"
        assert saved.cast[0].tmdb_id == 6193
        assert saved.cast[0].role == "Cobb"

    @pytest.mark.asyncio
    async def test_should_preserve_existing_cast_when_not_forced(self) -> None:
        # Counterpart to the above — without ``force``, the existing
        # cast (without ``tmdb_id``) must NOT be touched even if the
        # provider returns a richer payload.
        original_cast = [CastMember(name="Leonardo DiCaprio", tmdb_id=None)]
        movie = _make_movie().with_updates(cast=original_cast)
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = MediaMetadata(
            title="Inception",
            tmdb_id=27205,
            cast=[
                CreditPerson(name="Leonardo DiCaprio", tmdb_id=6193),
            ],
        )

        captured: dict[str, Movie] = {}

        async def _capture(m: Movie) -> Movie:
            captured["saved"] = m
            return m

        use_case, mocks = _set_up_enrichment(movie, provider)
        mocks.movies.save.side_effect = _capture

        await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        # ``tmdb_id`` stays None because the guard skipped the cast
        # update — the existing list wins.
        assert captured["saved"].cast[0].tmdb_id is None


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
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = _make_metadata()

        use_case, mocks = _set_up_enrichment(movie, provider)
        await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        saved = mocks.movies.save.call_args[0][0]
        assert saved.synopsis == "A mind-bending thriller."

    @pytest.mark.asyncio
    async def test_should_apply_genres_when_missing(self) -> None:
        movie = _make_movie()
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = _make_metadata()

        use_case, mocks = _set_up_enrichment(movie, provider)
        await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        saved = mocks.movies.save.call_args[0][0]
        assert {g.value for g in saved.genres} == {"Sci-Fi", "Action"}

    @pytest.mark.asyncio
    async def test_should_apply_cast_directors_writers(self) -> None:
        movie = _make_movie()
        metadata = MediaMetadata(
            title="Inception",
            tmdb_id=27205,
            cast=[
                CreditPerson(
                    name="Leonardo DiCaprio",
                    role="Cobb",
                    profile_url="https://image.tmdb.org/t/p/original/leo.jpg",
                ),
            ],
            directors=[CreditPerson(name="Christopher Nolan")],
            writers=[CreditPerson(name="Christopher Nolan")],
            content_rating="PG-13",
            trailer_url="https://youtube.com/abc",
        )
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = metadata

        use_case, mocks = _set_up_enrichment(movie, provider)
        await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        saved = mocks.movies.save.call_args[0][0]
        # Cast carries name + profile_path + role through the enrich
        # pipeline now — name-only data in tests would mask the
        # CreditPerson → CastMember plumbing the detail UI relies on.
        assert len(saved.cast) == 1
        assert saved.cast[0].name == "Leonardo DiCaprio"
        assert saved.cast[0].profile_path == "https://image.tmdb.org/t/p/original/leo.jpg"
        assert saved.cast[0].role == "Cobb"
        assert saved.directors == ["Christopher Nolan"]
        assert saved.writers == ["Christopher Nolan"]
        assert saved.content_rating == ContentRating("PG-13")
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
        provider = AsyncMock(spec=MetadataProvider)
        provider.search_movie.return_value = metadata

        use_case, mocks = _set_up_enrichment(movie, provider)
        await use_case.execute(EnrichMediaInput(media_id=str(movie.id)))

        saved = mocks.movies.save.call_args[0][0]
        assert saved.localized["pt-BR"]["title"] == "A Origem"
        assert saved.localized["pt-BR"]["synopsis"] == "Sonho dentro do sonho."
        assert saved.localized["pt-BR"]["genres"] == ["Ficção Científica"]
