"""Integration tests for the Watch Progress MediaLookupAdapter."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.value_objects import (
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
from src.modules.watch_progress.infrastructure.acl import MediaLookupAdapter


def _movie(
    movie_id: MovieId,
    title: str,
    poster: str | None = "/p/m.jpg",
    backdrop: str | None = "/b/m.jpg",
) -> Movie:
    return Movie(
        id=movie_id,
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        poster_path=ImageUrl(poster) if poster else None,
        backdrop_path=ImageUrl(backdrop) if backdrop else None,
        files=[
            MediaFile(
                file_path=FilePath(f"/movies/{title}.mkv"),
                file_size=1_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            ),
        ],
    )


def _series_with_episodes(
    series_id: SeriesId,
    title: str,
    episodes: list[tuple[int, int, str]],
) -> Series:
    """Create a series with given (season, episode, title) triples."""
    series = Series(
        id=series_id,
        title=Title(title),
        start_year=Year(2024),
        poster_path=ImageUrl("/p/s.jpg"),
        backdrop_path=ImageUrl("/b/s.jpg"),
    )
    by_season: dict[int, list[Episode]] = {}
    for season_num, ep_num, ep_title in episodes:
        by_season.setdefault(season_num, []).append(
            Episode(
                id=EpisodeId.generate(),
                series_id=series_id,
                season_number=season_num,
                episode_number=ep_num,
                title=Title(ep_title),
                duration=Duration(1800),
                files=[
                    MediaFile(
                        file_path=FilePath(f"/series/{title}/s{season_num:02d}e{ep_num:02d}.mkv"),
                        file_size=500_000,
                        resolution=Resolution("1080p"),
                        is_primary=True,
                    ),
                ],
            )
        )

    for season_num, eps in by_season.items():
        season = Season(id=SeasonId.generate(), series_id=series_id, season_number=season_num)
        for ep in eps:
            season = season.with_episode(ep)
        series = series.with_season(season)

    return series


@pytest.mark.integration
class TestWatchProgressMediaLookupAdapter:
    """The adapter returns display-ready DTOs for the Watch Progress BC."""

    async def test_get_movie_returns_display_info(self, db_session: AsyncSession) -> None:
        movie_repo = SQLAlchemyMovieRepository(db_session)
        series_repo = SQLAlchemySeriesRepository(db_session)

        movie_id = MovieId.generate()
        await movie_repo.save(_movie(movie_id, "Inception"))

        adapter = MediaLookupAdapter(movie_repo, series_repo)
        result = await adapter.get_movie(str(movie_id), "en")

        assert result is not None
        assert result.media_id == str(movie_id)
        assert result.title == "Inception"
        assert result.poster_path == "/p/m.jpg"
        assert result.backdrop_path == "/b/m.jpg"

    async def test_get_movie_returns_none_for_missing_id(self, db_session: AsyncSession) -> None:
        movie_repo = SQLAlchemyMovieRepository(db_session)
        series_repo = SQLAlchemySeriesRepository(db_session)
        adapter = MediaLookupAdapter(movie_repo, series_repo)

        assert await adapter.get_movie("mov_missing00000", "en") is None

    async def test_get_series_with_episodes_returns_sorted_list(
        self, db_session: AsyncSession
    ) -> None:
        movie_repo = SQLAlchemyMovieRepository(db_session)
        series_repo = SQLAlchemySeriesRepository(db_session)

        series_id = SeriesId.generate()
        series = _series_with_episodes(
            series_id,
            "Breaking Bad",
            [(2, 1, "S02E01"), (1, 2, "S01E02"), (1, 1, "S01E01")],
        )
        await series_repo.save(series)

        adapter = MediaLookupAdapter(movie_repo, series_repo)
        result = await adapter.get_series_with_episodes(str(series_id), "en")

        assert result is not None
        assert result.title == "Breaking Bad"
        assert [(e.season_number, e.episode_number) for e in result.episodes] == [
            (1, 1),
            (1, 2),
            (2, 1),
        ]
        assert [e.title for e in result.episodes] == ["S01E01", "S01E02", "S02E01"]
        assert all(e.duration_seconds == 1800 for e in result.episodes)

    async def test_get_series_returns_none_for_missing_id(self, db_session: AsyncSession) -> None:
        movie_repo = SQLAlchemyMovieRepository(db_session)
        series_repo = SQLAlchemySeriesRepository(db_session)
        adapter = MediaLookupAdapter(movie_repo, series_repo)

        assert await adapter.get_series_with_episodes("ser_missing00000", "en") is None
