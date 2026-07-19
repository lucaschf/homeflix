"""Integration tests for the artwork-mirror repo methods (ADR-029).

Exercises ``find_with_remote_artwork`` + ``update_movie_artwork`` on the
real SQLite-backed ``SQLAlchemyMovieRepository``: the LIKE-``http%``
filter selects only titles with a still-remote URL, and the targeted
column update swaps the URL without touching the rest of the row.
"""

import pytest
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
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)

_REMOTE = "https://image.tmdb.org/t/p/original/poster.jpg"
_LOCAL = "/api/v1/artwork/deadbeefdeadbeef.jpg"


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
