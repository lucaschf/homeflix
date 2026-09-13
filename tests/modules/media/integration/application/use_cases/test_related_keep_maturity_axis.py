"""The related-titles carousels keep both visibility axes (ADR-035 §11).

``GetRelatedMoviesUseCase`` and ``GetRelatedSeriesUseCase`` look up the
source title with ``find_by_id`` before asking TMDB for recommendations.
Only the two detail use cases fetch on the library axis alone (they need
to know the title exists to answer 403); the carousels pass the whole
policy, so an over-age source yields an empty carousel — not a list of
recommendations that confirms the title exists — and over-age
recommendations never make it in.

Driven through the real repositories and UoW; only the metadata
provider and the profile policy are stand-ins.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
)
from src.modules.media.application.use_cases.get_related_movies import (
    GetRelatedMoviesInput,
    GetRelatedMoviesUseCase,
)
from src.modules.media.application.use_cases.get_related_series import (
    GetRelatedSeriesInput,
    GetRelatedSeriesUseCase,
)
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    SeriesId,
    Title,
    TmdbId,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)
from src.modules.metadata.application.ports.metadata_provider_port import MetadataProvider
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import AgeRating, Certification, ContentRating, RatingSystem
from src.shared_kernel.value_objects.profile_id import ProfileId

_LIBRARY_ID = "lib_maturity0001"
_PROFILE_ID = "prf_test12345678"

_LIMITED = ViewingPolicy(allowed_library_ids=[_LIBRARY_ID], maturity_limit=AgeRating(12))

_WITHIN_SOURCE_TMDB = 100
_WITHIN_PICK_TMDB = 101
_OVER_AGE_TMDB = 102


class _FixedViewingPolicy(ProfileViewingPolicyPort):
    """Answer every profile with one policy — the Identity adapter is not under test."""

    def __init__(self, policy: ViewingPolicy) -> None:
        self._policy = policy

    async def find_for_profile(self, profile_id: ProfileId) -> ViewingPolicy:
        return self._policy


def _certification(age: int) -> Certification:
    return Certification(
        system=RatingSystem.BR_DEJUS,
        label=ContentRating(str(age)),
        minimum_age=AgeRating(age),
    )


def _movie(title: str, age: int, tmdb_id: int) -> Movie:
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
        tmdb_id=TmdbId(tmdb_id),
    )


def _series(title: str, age: int, tmdb_id: int) -> Series:
    return Series(
        library_id=_LIBRARY_ID,
        id=SeriesId.generate(),
        title=Title(title),
        start_year=Year(2020),
        certification=_certification(age),
        tmdb_id=TmdbId(tmdb_id),
    )


def _provider(recommendations: list[int]) -> AsyncMock:
    provider = AsyncMock(spec=MetadataProvider)
    provider.get_movie_recommendations.return_value = recommendations
    provider.get_series_recommendations.return_value = recommendations
    return provider


@pytest.mark.integration
class TestRelatedMoviesKeepTheMaturityAxis:
    """The movie carousel never reveals or recommends an over-age movie."""

    async def test_over_age_source_yields_an_empty_carousel(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SQLAlchemyMovieRepository(session)
            source = await repo.save(_movie("Over Age Source", 16, _OVER_AGE_TMDB))
            await repo.save(_movie("Within Pick", 10, _WITHIN_PICK_TMDB))
            await session.commit()
        provider = _provider([_WITHIN_PICK_TMDB])
        use_case = GetRelatedMoviesUseCase(
            SqlAlchemyMediaUnitOfWorkFactory(session_factory),
            provider,
            _FixedViewingPolicy(_LIMITED),
        )

        result = await use_case.execute(
            GetRelatedMoviesInput(profile_id=_PROFILE_ID, movie_id=str(source.id))
        )

        assert result == []
        provider.get_movie_recommendations.assert_not_awaited()

    async def test_over_age_recommendation_is_left_out(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SQLAlchemyMovieRepository(session)
            source = await repo.save(_movie("Within Source", 10, _WITHIN_SOURCE_TMDB))
            pick = await repo.save(_movie("Within Pick", 0, _WITHIN_PICK_TMDB))
            await repo.save(_movie("Over Age Pick", 16, _OVER_AGE_TMDB))
            await session.commit()
        use_case = GetRelatedMoviesUseCase(
            SqlAlchemyMediaUnitOfWorkFactory(session_factory),
            _provider([_OVER_AGE_TMDB, _WITHIN_PICK_TMDB]),
            _FixedViewingPolicy(_LIMITED),
        )

        result = await use_case.execute(
            GetRelatedMoviesInput(profile_id=_PROFILE_ID, movie_id=str(source.id))
        )

        assert [movie.id for movie in result] == [str(pick.id)]


@pytest.mark.integration
class TestRelatedSeriesKeepTheMaturityAxis:
    """The series carousel never reveals or recommends an over-age series."""

    async def test_over_age_source_yields_an_empty_carousel(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SQLAlchemySeriesRepository(session)
            source = await repo.save(_series("Over Age Source", 16, _OVER_AGE_TMDB))
            await repo.save(_series("Within Pick", 10, _WITHIN_PICK_TMDB))
            await session.commit()
        provider = _provider([_WITHIN_PICK_TMDB])
        use_case = GetRelatedSeriesUseCase(
            SqlAlchemyMediaUnitOfWorkFactory(session_factory),
            provider,
            _FixedViewingPolicy(_LIMITED),
        )

        result = await use_case.execute(
            GetRelatedSeriesInput(profile_id=_PROFILE_ID, series_id=str(source.id))
        )

        assert result == []
        provider.get_series_recommendations.assert_not_awaited()

    async def test_over_age_recommendation_is_left_out(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            repo = SQLAlchemySeriesRepository(session)
            source = await repo.save(_series("Within Source", 10, _WITHIN_SOURCE_TMDB))
            pick = await repo.save(_series("Within Pick", 0, _WITHIN_PICK_TMDB))
            await repo.save(_series("Over Age Pick", 16, _OVER_AGE_TMDB))
            await session.commit()
        use_case = GetRelatedSeriesUseCase(
            SqlAlchemyMediaUnitOfWorkFactory(session_factory),
            _provider([_OVER_AGE_TMDB, _WITHIN_PICK_TMDB]),
            _FixedViewingPolicy(_LIMITED),
        )

        result = await use_case.execute(
            GetRelatedSeriesInput(profile_id=_PROFILE_ID, series_id=str(source.id))
        )

        assert [series.id for series in result] == [str(pick.id)]
