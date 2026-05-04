"""Integration tests for MediaCountQueryAdapter."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.library.infrastructure.acl import MediaCountQueryAdapter
from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    SeasonId,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)

_LIBRARY_ID = "lib_test12345678"


def _movie(title: str, file_path: str) -> Movie:
    return Movie(
        library_id=_LIBRARY_ID,
        id=MovieId.generate(),
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(file_path),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            ),
        ],
    )


def _series_with_episode(title: str, file_path: str) -> Series:
    series = Series.create(library_id=_LIBRARY_ID, title=title, start_year=2024)
    assert series.id is not None
    season = Season(id=SeasonId.generate(), series_id=series.id, season_number=1)
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=series.id,
        season_number=1,
        episode_number=1,
        title=Title("Pilot"),
        duration=Duration(3600),
        files=[
            MediaFile(
                file_path=FilePath(file_path),
                file_size=500_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            ),
        ],
    )
    return series.with_season(season.with_episode(episode))


@pytest.mark.integration
class TestMediaCountQueryAdapter:
    """The adapter delegates counts to the Media Unit of Work."""

    async def test_count_movies_under_paths_matches_repository(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_repo = SQLAlchemyMovieRepository(db_session)
        await movie_repo.save(_movie("A", "/movies/a.mkv"))
        await movie_repo.save(_movie("B", "/movies/b.mkv"))
        await movie_repo.save(_movie("C", "/other/c.mkv"))
        await db_session.commit()

        adapter = MediaCountQueryAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))

        assert await adapter.count_movies_under_paths(["/movies"]) == 2
        assert await adapter.count_movies_under_paths(["/other"]) == 1
        assert await adapter.count_movies_under_paths(["/missing"]) == 0

    async def test_count_series_under_paths_matches_repository(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        series_repo = SQLAlchemySeriesRepository(db_session)
        await series_repo.save(_series_with_episode("Series A", "/series/a/s01e01.mkv"))
        await series_repo.save(_series_with_episode("Series B", "/series/b/s01e01.mkv"))
        await db_session.commit()

        adapter = MediaCountQueryAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))

        assert await adapter.count_series_under_paths(["/series"]) == 2
        assert await adapter.count_series_under_paths(["/series/a"]) == 1
        assert await adapter.count_series_under_paths(["/missing"]) == 0

    async def test_empty_paths_returns_zero(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        adapter = MediaCountQueryAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))

        assert await adapter.count_movies_under_paths([]) == 0
        assert await adapter.count_series_under_paths([]) == 0
