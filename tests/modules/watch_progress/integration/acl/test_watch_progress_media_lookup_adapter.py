"""Integration tests for the Watch Progress MediaLookupAdapter.

Both methods must hand the caller's policy to the Media catalog on both
axes. The catalog is seeded with one title per way of being out of
reach — above the age limit, unrated, another library, soft-deleted,
never created — next to one title the policy permits, as a movie and as
a series.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)
from src.modules.watch_progress.infrastructure.acl import MediaLookupAdapter
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import AgeRating, Certification, ContentRating, RatingSystem

_LIBRARY_ID = "lib_test12345678"
_OTHER_LIBRARY_ID = "lib_other1234567"

_LIMITED = ViewingPolicy(allowed_library_ids=[_LIBRARY_ID], maturity_limit=AgeRating(12))
_LIBRARY_ONLY = ViewingPolicy.unrestricted([_LIBRARY_ID])
_DENY_ALL = ViewingPolicy(allowed_library_ids=[])

#: Seeded shapes: ``(key, library_id, age or None for unrated, soft-deleted)``.
_SHAPES: list[tuple[str, str, int | None, bool]] = [
    ("ten", _LIBRARY_ID, 10, False),
    ("sixteen", _LIBRARY_ID, 16, False),
    ("unrated", _LIBRARY_ID, None, False),
    ("other_library", _OTHER_LIBRARY_ID, 10, False),
    ("deleted", _LIBRARY_ID, 10, True),
]


def _certification(age: int | None) -> Certification | None:
    if age is None:
        return None
    return Certification(
        system=RatingSystem.BR_DEJUS,
        label=ContentRating(str(age)),
        minimum_age=AgeRating(age),
    )


def _movie(
    movie_id: MovieId,
    title: str,
    *,
    library_id: str = _LIBRARY_ID,
    age: int | None = 10,
) -> Movie:
    return Movie(
        library_id=library_id,
        id=movie_id,
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        poster_path=ImageUrl("/p/m.jpg"),
        backdrop_path=ImageUrl("/b/m.jpg"),
        files=[
            MediaFile(
                file_path=FilePath(f"/movies/{title}.mkv"),
                file_size=1_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            ),
        ],
        certification=_certification(age),
    )


def _series_with_episodes(
    series_id: SeriesId,
    title: str,
    episodes: list[tuple[int, int, str]],
    *,
    library_id: str = _LIBRARY_ID,
    age: int | None = 10,
) -> Series:
    """Create a series with given (season, episode, title) triples."""
    series = Series(
        library_id=library_id,
        id=series_id,
        title=Title(title),
        start_year=Year(2024),
        poster_path=ImageUrl("/p/s.jpg"),
        backdrop_path=ImageUrl("/b/s.jpg"),
        certification=_certification(age),
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


class _Seeded:
    """Ids of the seeded titles, by shape key."""

    def __init__(self) -> None:
        self.movies: dict[str, MovieId] = {}
        self.series: dict[str, SeriesId] = {}
        self.missing_movie = MovieId("mov_missing00000")
        self.missing_series = SeriesId("ser_missing00000")

    def all_movie_ids(self) -> list[MovieId]:
        return [*self.movies.values(), self.missing_movie]

    def all_series_ids(self) -> list[SeriesId]:
        return [*self.series.values(), self.missing_series]


@pytest.fixture
async def seeded(db_session: AsyncSession) -> _Seeded:
    """Seed every shape once as a movie and once as a series."""
    ids = _Seeded()
    movie_repo = SQLAlchemyMovieRepository(db_session)
    series_repo = SQLAlchemySeriesRepository(db_session)
    for key, library_id, age, deleted in _SHAPES:
        movie_id = MovieId.generate()
        await movie_repo.save(_movie(movie_id, f"Movie {key}", library_id=library_id, age=age))
        series_id = SeriesId.generate()
        await series_repo.save(
            _series_with_episodes(
                series_id,
                f"Series {key}",
                [(2, 1, "S02E01"), (1, 2, "S01E02"), (1, 1, "S01E01")],
                library_id=library_id,
                age=age,
            )
        )
        if deleted:
            assert await movie_repo.delete(movie_id)
            assert await series_repo.delete(series_id)
        ids.movies[key] = movie_id
        ids.series[key] = series_id
    await db_session.commit()
    return ids


def _adapter(session_factory: async_sessionmaker[AsyncSession]) -> MediaLookupAdapter:
    return MediaLookupAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))


@pytest.mark.integration
class TestFindVisibleTitles:
    """``find_visible_titles`` answers through the caller's policy."""

    async def test_limited_policy_keeps_only_permitted_titles(
        self,
        seeded: _Seeded,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        visible = await _adapter(session_factory).find_visible_titles(
            movie_ids=seeded.all_movie_ids(),
            series_ids=seeded.all_series_ids(),
            policy=_LIMITED,
        )

        assert visible == frozenset({seeded.movies["ten"].value, seeded.series["ten"].value})

    async def test_library_only_policy_keeps_every_age(
        self,
        seeded: _Seeded,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        visible = await _adapter(session_factory).find_visible_titles(
            movie_ids=seeded.all_movie_ids(),
            series_ids=seeded.all_series_ids(),
            policy=_LIBRARY_ONLY,
        )

        in_reach = ("ten", "sixteen", "unrated")
        assert visible == frozenset(
            [seeded.movies[key].value for key in in_reach]
            + [seeded.series[key].value for key in in_reach]
        )

    async def test_empty_acl_sees_nothing(
        self,
        seeded: _Seeded,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        visible = await _adapter(session_factory).find_visible_titles(
            movie_ids=seeded.all_movie_ids(),
            series_ids=seeded.all_series_ids(),
            policy=_DENY_ALL,
        )

        assert visible == frozenset()


@pytest.mark.integration
class TestFindDisplayInfo:
    """``find_display_info`` returns display DTOs for visible titles only."""

    async def test_limited_policy_returns_only_permitted_titles(
        self,
        seeded: _Seeded,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        batch = await _adapter(session_factory).find_display_info(
            movie_ids=seeded.all_movie_ids(),
            series_ids=seeded.all_series_ids(),
            lang="en",
            policy=_LIMITED,
        )

        assert set(batch.movies) == {seeded.movies["ten"].value}
        assert set(batch.series) == {seeded.series["ten"].value}

    async def test_movie_display_info(
        self,
        seeded: _Seeded,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = seeded.movies["ten"]

        batch = await _adapter(session_factory).find_display_info(
            movie_ids=[movie_id], series_ids=[], lang="en", policy=_LIMITED
        )

        movie = batch.movies[movie_id.value]
        assert movie.media_id == movie_id.value
        assert movie.title == "Movie ten"
        assert movie.poster_path == "/p/m.jpg"
        assert movie.backdrop_path == "/b/m.jpg"

    async def test_series_display_info_has_sorted_episodes(
        self,
        seeded: _Seeded,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        series_id = seeded.series["ten"]

        batch = await _adapter(session_factory).find_display_info(
            movie_ids=[], series_ids=[series_id], lang="en", policy=_LIMITED
        )

        series = batch.series[series_id.value]
        assert series.series_id == series_id.value
        assert series.title == "Series ten"
        assert [(e.season_number, e.episode_number) for e in series.episodes] == [
            (1, 1),
            (1, 2),
            (2, 1),
        ]
        assert [e.title for e in series.episodes] == ["S01E01", "S01E02", "S02E01"]
        assert all(e.duration_seconds == 1800 for e in series.episodes)

    async def test_empty_acl_returns_nothing(
        self,
        seeded: _Seeded,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        batch = await _adapter(session_factory).find_display_info(
            movie_ids=seeded.all_movie_ids(),
            series_ids=seeded.all_series_ids(),
            lang="en",
            policy=_DENY_ALL,
        )

        assert batch.movies == {}
        assert batch.series == {}
