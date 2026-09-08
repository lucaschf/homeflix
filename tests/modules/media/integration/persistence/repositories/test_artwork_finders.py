"""Integration tests for the artwork-mirror repo methods (ADR-029).

Exercises ``find_with_remote_artwork`` + ``update_movie_artwork`` on the
real SQLite-backed ``SQLAlchemyMovieRepository``: the LIKE-``http%``
filter selects only titles with a still-remote URL, and the targeted
column update swaps the URL without touching the rest of the row. The
localized variants walk the ``localized`` JSON blob with ``json_each``
and rewrite one locale's artwork fields with ``json_set``.
"""

import json

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.value_objects import (
    ArtworkColumns,
    Duration,
    EpisodeId,
    FilePath,
    ImageUrl,
    MediaFile,
    MovieId,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
    Year,
)
from src.modules.media.domain.value_objects.localized_metadata import (
    LocalizedField,
    LocalizedMetadata,
)
from src.modules.media.infrastructure.persistence.mappers._localized import load_localized
from src.modules.media.infrastructure.persistence.models import MovieModel
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)

_REMOTE = "https://image.tmdb.org/t/p/original/poster.jpg"
_LOCAL = "/api/v1/artwork/deadbeefdeadbeef.jpg"
_LOCALIZED = {
    "pt-BR": {"title": "Aviões", "poster_path": _REMOTE, "genres": ["Ação"]},
    "en": {"logo_path": _LOCAL},
}


def _movie(title: str, path: str, **kwargs: object) -> Movie:
    return Movie(
        library_id="lib_test12345678",
        id=MovieId.generate(),
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(path),
                file_size=1_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
        **kwargs,
    )


@pytest.mark.integration
class TestFindWithRemoteArtwork:
    async def test_should_return_only_titles_with_a_remote_url(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        remote = _movie(
            "Remote",
            "/movies/a.mkv",
            poster_path=ImageUrl(_REMOTE),
            backdrop_path=ImageUrl(_LOCAL),  # already local
        )
        local_only = _movie("Local", "/movies/b.mkv", poster_path=ImageUrl(_LOCAL))
        no_art = _movie("Bare", "/movies/c.mkv")
        for movie in (remote, local_only, no_art):
            await repo.save(movie)

        rows = await repo.find_with_remote_artwork(limit=10)

        assert len(rows) == 1
        assert rows[0].media_id == str(remote.id)
        assert rows[0].artwork.poster == ImageUrl(_REMOTE)
        assert rows[0].artwork.backdrop == ImageUrl(_LOCAL)

    async def test_should_respect_the_limit(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        for i in range(3):
            await repo.save(_movie(f"M{i}", f"/movies/m{i}.mkv", poster_path=ImageUrl(_REMOTE)))

        rows = await repo.find_with_remote_artwork(limit=2)

        assert len(rows) == 2


@pytest.mark.integration
class TestUpdateMovieArtwork:
    async def test_should_swap_remote_columns_for_local(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie(
            "Remote",
            "/movies/a.mkv",
            poster_path=ImageUrl(_REMOTE),
            backdrop_path=ImageUrl(_REMOTE),
        )
        await repo.save(movie)

        await repo.update_movie_artwork(
            _id(movie),
            ArtworkColumns(poster=ImageUrl(_LOCAL), backdrop=ImageUrl(_LOCAL), logo=None),
        )

        # The title now has no remote artwork, and the reloaded entity
        # carries the local references + an intact title.
        assert await repo.find_with_remote_artwork(limit=10) == []
        reloaded = await repo.find_by_id(_id(movie))
        assert reloaded is not None
        assert reloaded.poster_path == ImageUrl(_LOCAL)
        assert reloaded.backdrop_path == ImageUrl(_LOCAL)
        assert reloaded.logo_path is None
        assert reloaded.title == Title("Remote")


def _id(movie: Movie) -> MovieId:
    assert movie.id is not None
    return movie.id


def _localized(raw: dict[str, dict[str, object]]) -> LocalizedMetadata:
    return LocalizedMetadata.from_serializable(raw)  # type: ignore[arg-type]


async def _raw_localized(db_session: AsyncSession, movie: Movie) -> str | None:
    stmt = select(MovieModel.localized).where(MovieModel.external_id == str(_id(movie)))
    return (await db_session.execute(stmt)).scalar_one()


@pytest.mark.integration
class TestFindWithRemoteLocalizedArtwork:
    async def test_should_return_one_row_per_locale_with_a_remote_url(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie("Planes", "/movies/a.mkv", localized=_localized(_LOCALIZED))
        await repo.save(movie)

        rows = await repo.find_with_remote_localized_artwork(limit=10)

        # "en" only holds a local logo -> not a row; "pt-BR" is one row
        # carrying just the artwork fields of that locale.
        assert len(rows) == 1
        assert rows[0].media_id == str(_id(movie))
        assert rows[0].locale == "pt-BR"
        assert rows[0].artwork.poster == ImageUrl(_REMOTE)
        assert rows[0].artwork.backdrop is None
        assert rows[0].artwork.logo is None

    async def test_should_skip_titles_without_a_localized_blob(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        # A remote *column* URL is the other finder's business.
        await repo.save(_movie("Bare", "/movies/b.mkv", poster_path=ImageUrl(_REMOTE)))

        assert await repo.find_with_remote_localized_artwork(limit=10) == []

    async def test_should_exclude_soft_deleted_titles(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie("Gone", "/movies/c.mkv", localized=_localized(_LOCALIZED))
        await repo.save(movie)
        await repo.delete(_id(movie))

        assert await repo.find_with_remote_localized_artwork(limit=10) == []

    async def test_should_respect_the_limit_over_locale_rows(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        three_locales = {lang: {"backdrop_path": _REMOTE} for lang in ("de", "es-419", "pt-BR")}
        await repo.save(_movie("Many", "/movies/d.mkv", localized=_localized(three_locales)))

        rows = await repo.find_with_remote_localized_artwork(limit=2)

        assert [row.locale for row in rows] == ["de", "es-419"]


@pytest.mark.integration
class TestUpdateMovieLocalizedArtwork:
    async def test_should_set_only_the_given_fields_and_keep_the_rest(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie("Planes", "/movies/a.mkv", localized=_localized(_LOCALIZED))
        await repo.save(movie)

        await repo.update_movie_localized_artwork(
            _id(movie), "pt-BR", ArtworkColumns(poster=ImageUrl(_LOCAL))
        )

        assert await repo.find_with_remote_localized_artwork(limit=10) == []
        reloaded = await repo.find_by_id(_id(movie))
        assert reloaded is not None
        localized = reloaded.localized
        assert localized.text(LocalizedField.POSTER_PATH, "pt-BR") == _LOCAL
        # Everything else in the blob — same locale and the other one —
        # is exactly as enriched.
        assert localized.text(LocalizedField.TITLE, "pt-BR") == "Aviões"
        assert localized.genres("pt-BR") == ("Ação",)
        assert localized.text(LocalizedField.LOGO_PATH, "en") == _LOCAL

    async def test_should_round_trip_through_the_localized_mapper(
        self, db_session: AsyncSession
    ) -> None:
        # ADR-023 fidelity: the blob ``json_set`` leaves behind must be
        # the wire shape the mapper reads and writes, nothing more.
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie("Planes", "/movies/a.mkv", localized=_localized(_LOCALIZED))
        await repo.save(movie)

        await repo.update_movie_localized_artwork(
            _id(movie), "pt-BR", ArtworkColumns(poster=ImageUrl(_LOCAL))
        )

        raw = await _raw_localized(db_session, movie)
        assert raw is not None
        expected = json.loads(json.dumps(_LOCALIZED))
        expected["pt-BR"]["poster_path"] = _LOCAL
        assert load_localized(raw).to_serializable() == expected

    async def test_should_not_canonicalize_the_locale_key(self, db_session: AsyncSession) -> None:
        # The updater must hit the entry the finder read, even when its
        # key is not in canonical BCP 47 casing — no second entry appears.
        # The value object canonicalizes keys on construction, so a legacy
        # blob has to be planted straight into the column.
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie("Legacy", "/movies/e.mkv")
        await repo.save(movie)
        await db_session.execute(
            update(MovieModel)
            .where(MovieModel.external_id == str(_id(movie)))
            .values(localized=json.dumps({"pt-br": {"logo_path": _REMOTE}}))
        )
        rows = await repo.find_with_remote_localized_artwork(limit=10)
        assert rows[0].locale == "pt-br"

        await repo.update_movie_localized_artwork(
            _id(movie), rows[0].locale, ArtworkColumns(logo=ImageUrl(_LOCAL))
        )

        raw = await _raw_localized(db_session, movie)
        assert raw is not None
        assert json.loads(raw) == {"pt-br": {"logo_path": _LOCAL}}

    async def test_should_remove_a_field_given_as_none(self, db_session: AsyncSession) -> None:
        # The mirror drops a reference the provider answered 404 for:
        # the field leaves the locale entry, the rest of it survives, and
        # the finder stops returning the row.
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie("Planes", "/movies/a.mkv", localized=_localized(_LOCALIZED))
        await repo.save(movie)

        await repo.update_movie_localized_artwork(_id(movie), "pt-BR", ArtworkColumns())

        assert await repo.find_with_remote_localized_artwork(limit=10) == []
        raw = await _raw_localized(db_session, movie)
        assert raw is not None
        expected = json.loads(json.dumps(_LOCALIZED))
        del expected["pt-BR"]["poster_path"]
        assert load_localized(raw).to_serializable() == expected

    async def test_should_reject_an_unsafe_locale_key(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie("Planes", "/movies/a.mkv", localized=_localized(_LOCALIZED))
        await repo.save(movie)

        with pytest.raises(ValueError, match="unsafe locale key"):
            await repo.update_movie_localized_artwork(
                _id(movie), 'pt".x', ArtworkColumns(poster=ImageUrl(_LOCAL))
            )

    async def test_should_be_a_noop_when_the_blob_is_null(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie("Bare", "/movies/b.mkv")
        await repo.save(movie)

        await repo.update_movie_localized_artwork(
            _id(movie), "pt-BR", ArtworkColumns(poster=ImageUrl(_LOCAL))
        )

        assert await _raw_localized(db_session, movie) is None


def _series_with_one_episode(title: str, **kwargs: object) -> Series:
    sid = SeriesId.generate()
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=sid,
        season_number=1,
        episode_number=1,
        title=Title("E1"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath("/series/s01e01.mkv"),
                file_size=500_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    season = Season(
        id=SeasonId.generate(),
        series_id=sid,
        season_number=1,
        title=Title("Season 1"),
        episodes=[episode],
    )
    return Series(
        library_id="lib_test12345678",
        id=sid,
        title=Title(title),
        start_year=Year(2020),
        seasons=[season],
        **kwargs,
    )


@pytest.mark.integration
class TestSeriesArtwork:
    async def test_should_find_and_update_without_touching_children(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _series_with_one_episode("Remote", poster_path=ImageUrl(_REMOTE))
        await repo.save(series)
        assert series.id is not None

        rows = await repo.find_with_remote_artwork(limit=10)
        assert len(rows) == 1
        assert rows[0].media_id == str(series.id)

        await repo.update_series_artwork(
            series.id, ArtworkColumns(poster=ImageUrl(_LOCAL), backdrop=None, logo=None)
        )

        assert await repo.find_with_remote_artwork(limit=10) == []
        reloaded = await repo.find_by_id(series.id)
        assert reloaded is not None
        assert reloaded.poster_path == ImageUrl(_LOCAL)
        # The whole reason for the direct column update: seasons/episodes
        # must survive an artwork update untouched.
        assert len(reloaded.seasons) == 1
        assert len(reloaded.seasons[0].episodes) == 1


@pytest.mark.integration
class TestSeriesLocalizedArtwork:
    async def test_should_find_and_update_without_touching_children(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _series_with_one_episode("Remote", localized=_localized(_LOCALIZED))
        await repo.save(series)
        assert series.id is not None

        rows = await repo.find_with_remote_localized_artwork(limit=10)
        assert [(row.media_id, row.locale) for row in rows] == [(str(series.id), "pt-BR")]

        await repo.update_series_localized_artwork(
            series.id, "pt-BR", ArtworkColumns(poster=ImageUrl(_LOCAL))
        )

        assert await repo.find_with_remote_localized_artwork(limit=10) == []
        reloaded = await repo.find_by_id(series.id)
        assert reloaded is not None
        assert reloaded.localized.text(LocalizedField.POSTER_PATH, "pt-BR") == _LOCAL
        assert reloaded.localized.text(LocalizedField.TITLE, "pt-BR") == "Aviões"
        assert len(reloaded.seasons) == 1
        assert len(reloaded.seasons[0].episodes) == 1


def _series_with_season_poster(poster: str) -> tuple[Series, SeasonId, SeriesId]:
    sid = SeriesId.generate()
    season_id = SeasonId.generate()
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=sid,
        season_number=1,
        episode_number=1,
        title=Title("E1"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath("/series/s01e01.mkv"),
                file_size=500_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    season = Season(
        id=season_id,
        series_id=sid,
        season_number=1,
        title=Title("Season 1"),
        poster_path=ImageUrl(poster),
        episodes=[episode],
    )
    series = Series(
        library_id="lib_test12345678",
        id=sid,
        title=Title("With Season"),
        start_year=Year(2020),
        seasons=[season],
    )
    return series, season_id, sid


@pytest.mark.integration
class TestSeasonArtwork:
    async def test_should_find_and_update_season_poster(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series, season_id, series_id = _series_with_season_poster(_REMOTE)
        await repo.save(series)

        rows = await repo.find_seasons_with_remote_poster(limit=10)
        assert len(rows) == 1
        assert rows[0].media_id == str(season_id)
        assert rows[0].artwork.poster == ImageUrl(_REMOTE)

        await repo.update_season_artwork(
            season_id, ArtworkColumns(poster=ImageUrl(_LOCAL), backdrop=None, logo=None)
        )

        assert await repo.find_seasons_with_remote_poster(limit=10) == []
        reloaded = await repo.find_by_id(series_id)
        assert reloaded is not None
        assert reloaded.seasons[0].poster_path == ImageUrl(_LOCAL)
        # The episode survives a season-poster update untouched.
        assert len(reloaded.seasons[0].episodes) == 1


def _series_with_episode_thumbnail(thumb: str) -> tuple[Series, EpisodeId, SeriesId]:
    sid = SeriesId.generate()
    episode_id = EpisodeId.generate()
    episode = Episode(
        id=episode_id,
        series_id=sid,
        season_number=1,
        episode_number=1,
        title=Title("E1"),
        duration=Duration(2700),
        thumbnail_path=ImageUrl(thumb),
        files=[
            MediaFile(
                file_path=FilePath("/series/s01e01.mkv"),
                file_size=500_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    season = Season(
        id=SeasonId.generate(),
        series_id=sid,
        season_number=1,
        title=Title("Season 1"),
        episodes=[episode],
    )
    series = Series(
        library_id="lib_test12345678",
        id=sid,
        title=Title("With Episode"),
        start_year=Year(2020),
        seasons=[season],
    )
    return series, episode_id, sid


@pytest.mark.integration
class TestEpisodeArtwork:
    async def test_should_find_and_update_episode_thumbnail(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series, episode_id, series_id = _series_with_episode_thumbnail(_REMOTE)
        await repo.save(series)

        rows = await repo.find_episodes_with_remote_thumbnail(limit=10)
        assert len(rows) == 1
        assert rows[0].media_id == str(episode_id)
        assert rows[0].artwork.still == ImageUrl(_REMOTE)

        await repo.update_episode_thumbnail(episode_id, ArtworkColumns(still=ImageUrl(_LOCAL)))

        assert await repo.find_episodes_with_remote_thumbnail(limit=10) == []
        reloaded = await repo.find_by_id(series_id)
        assert reloaded is not None
        assert reloaded.seasons[0].episodes[0].thumbnail_path == ImageUrl(_LOCAL)
