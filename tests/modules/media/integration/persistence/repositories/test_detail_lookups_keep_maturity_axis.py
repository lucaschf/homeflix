"""Single-title lookups keep both visibility axes (ADR-035 §11).

The detail use cases fetch on the library axis alone and check the age
in the domain, because a 403 has to know the title exists. That is a
choice made in those two use cases, not in the repository: ``find_by_id``
still applies the whole ``ViewingPolicy`` it is handed, and so does
everything that delegates to it. ``find_by_episode_id`` hands its policy
straight to ``find_by_id`` — were the repository relaxed to library-only
for the detail page's sake, an episode lookup would start returning
over-age series without any caller asking for it.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
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
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import AgeRating, Certification, ContentRating, RatingSystem

_LIBRARY_ID = "lib_maturity0001"
_LIMIT = 12

_LIMITED = ViewingPolicy(allowed_library_ids=[_LIBRARY_ID], maturity_limit=AgeRating(_LIMIT))
_NO_AGE_LIMIT = ViewingPolicy.unrestricted([_LIBRARY_ID])


def _certification(age: int) -> Certification:
    return Certification(
        system=RatingSystem.BR_DEJUS,
        label=ContentRating(str(age)),
        minimum_age=AgeRating(age),
    )


def _movie(title: str, age: int) -> Movie:
    return Movie(
        library_id=_LIBRARY_ID,
        id=MovieId.generate(),
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(f"/{_LIBRARY_ID}/{title}.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
        certification=_certification(age),
    )


def _series(title: str, age: int) -> Series:
    series_id = SeriesId.generate()
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=series_id,
        season_number=1,
        episode_number=1,
        title=Title("Pilot"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath(f"/{_LIBRARY_ID}/{title}/s01e01.mkv"),
                file_size=500_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    return Series(
        library_id=_LIBRARY_ID,
        id=series_id,
        title=Title(title),
        start_year=Year(2020),
        seasons=[
            Season(
                id=SeasonId.generate(),
                series_id=series_id,
                season_number=1,
                title=Title("Season 1"),
                episodes=[episode],
            )
        ],
        certification=_certification(age),
    )


@pytest.mark.integration
class TestDetailLookupsKeepTheMaturityAxis:
    """A limited policy hides over-age titles from every single-title read."""

    async def test_movie_find_by_id_applies_the_age_limit(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SQLAlchemyMovieRepository(session)
            over_age = await repo.save(_movie("Over Age Movie", 16))
            within = await repo.save(_movie("Within Movie", 10))
            await session.commit()

        async with session_factory() as session:
            repo = SQLAlchemyMovieRepository(session)
            assert over_age.id is not None and within.id is not None
            assert await repo.find_by_id(over_age.id, policy=_LIMITED) is None
            assert await repo.find_by_id(within.id, policy=_LIMITED) is not None
            # The title is there — only the age axis hides it.
            assert await repo.find_by_id(over_age.id, policy=_NO_AGE_LIMIT) is not None

    async def test_series_find_by_id_applies_the_age_limit(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SQLAlchemySeriesRepository(session)
            over_age = await repo.save(_series("Over Age Show", 16))
            within = await repo.save(_series("Within Show", 10))
            await session.commit()

        async with session_factory() as session:
            repo = SQLAlchemySeriesRepository(session)
            assert over_age.id is not None and within.id is not None
            assert await repo.find_by_id(over_age.id, policy=_LIMITED) is None
            assert await repo.find_by_id(within.id, policy=_LIMITED) is not None
            assert await repo.find_by_id(over_age.id, policy=_NO_AGE_LIMIT) is not None

    async def test_find_by_episode_id_applies_the_age_limit(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SQLAlchemySeriesRepository(session)
            over_age = await repo.save(_series("Over Age Show", 16))
            within = await repo.save(_series("Within Show", 10))
            await session.commit()

        over_age_episode = over_age.seasons[0].episodes[0].id
        within_episode = within.seasons[0].episodes[0].id
        assert over_age_episode is not None and within_episode is not None

        async with session_factory() as session:
            repo = SQLAlchemySeriesRepository(session)
            assert await repo.find_by_episode_id(over_age_episode, policy=_LIMITED) is None
            found = await repo.find_by_episode_id(within_episode, policy=_LIMITED)
            assert found is not None
            assert str(found.id) == str(within.id)
