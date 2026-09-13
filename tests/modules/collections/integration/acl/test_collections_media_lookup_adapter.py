"""Integration tests for the Collections MediaLookupAdapter."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.collections.infrastructure.acl import MediaLookupAdapter
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    Genre,
    HdrFormat,
    ImageUrl,
    MediaFile,
    MovieId,
    Resolution,
    SeriesId,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.models.movie import MovieModel
from src.modules.media.infrastructure.persistence.models.series import SeriesModel
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)
from src.shared_kernel.value_objects import (
    AgeRating,
    Certification,
    ContentRating,
    MediaType,
    RatingSystem,
)

_LIBRARY_ID = "lib_test12345678"
_OTHER_LIBRARY_ID = "lib_other1234567"


def _certification(age: int) -> Certification:
    return Certification(
        system=RatingSystem.BR_DEJUS,
        label=ContentRating(str(age)),
        minimum_age=AgeRating(age),
    )


def _movie(
    movie_id: MovieId,
    title: str,
    poster: str | None = None,
    *,
    library_id: str = _LIBRARY_ID,
    certification: Certification | None = None,
) -> Movie:
    return Movie(
        library_id=library_id,
        id=movie_id,
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        poster_path=ImageUrl(poster) if poster else None,
        files=[
            MediaFile(
                file_path=FilePath(f"/movies/{title}.mkv"),
                file_size=1_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            ),
        ],
        certification=certification,
    )


def _series(
    series_id: SeriesId,
    title: str,
    poster: str | None = None,
    *,
    certification: Certification | None = None,
) -> Series:
    return Series(
        library_id=_LIBRARY_ID,
        id=series_id,
        title=Title(title),
        start_year=Year(2024),
        poster_path=ImageUrl(poster) if poster else None,
        certification=certification,
    )


@pytest.mark.integration
class TestCollectionsMediaLookupAdapter:
    """The adapter resolves titles + posters for the Collections BC."""

    async def test_get_many_resolves_movies_and_series(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = MovieId.generate()
        series_id = SeriesId.generate()
        await SQLAlchemyMovieRepository(db_session).save(
            _movie(movie_id, "Inception", "/p/inception.jpg"),
        )
        await SQLAlchemySeriesRepository(db_session).save(
            _series(series_id, "Breaking Bad", "/p/bb.jpg"),
        )
        await db_session.commit()

        adapter = MediaLookupAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))

        summaries = await adapter.get_many([str(movie_id)], [str(series_id)], "en")

        movie_summary = summaries[(MediaType.MOVIE, str(movie_id))]
        assert movie_summary.title == "Inception"
        assert movie_summary.poster_path == "/p/inception.jpg"
        assert movie_summary.year == 2024
        assert movie_summary.runtime_seconds == 7200
        assert movie_summary.resolution == "1080p"
        assert movie_summary.hdr is False

        series_summary = summaries[(MediaType.SERIES, str(series_id))]
        assert series_summary.title == "Breaking Bad"
        assert series_summary.poster_path == "/p/bb.jpg"
        assert series_summary.year == 2024
        # Runtime/resolution/HDR are episode-derived → not surfaced for series.
        assert series_summary.runtime_seconds is None
        assert series_summary.resolution is None
        assert series_summary.hdr is False

    async def test_movie_enrichment_derives_genres_and_best_quality(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = MovieId.generate()
        movie = Movie(
            library_id=_LIBRARY_ID,
            id=movie_id,
            title=Title("Dune"),
            year=Year(2021),
            duration=Duration(9300),
            genres=[Genre("Science Fiction"), Genre("Adventure")],
            files=[
                MediaFile(
                    file_path=FilePath("/movies/dune-1080.mkv"),
                    file_size=1_000_000,
                    resolution=Resolution("1080p"),
                    is_primary=True,
                ),
                MediaFile(
                    file_path=FilePath("/movies/dune-4k.mkv"),
                    file_size=4_000_000,
                    resolution=Resolution("4K"),
                    hdr_format=HdrFormat.DOLBY_VISION,
                ),
            ],
        )
        await SQLAlchemyMovieRepository(db_session).save(movie)
        await db_session.commit()

        adapter = MediaLookupAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))
        summaries = await adapter.get_many([str(movie_id)], [], "en")

        summary = summaries[(MediaType.MOVIE, str(movie_id))]
        assert summary.genres == ("Science Fiction", "Adventure")
        # best_file is the highest-resolution variant → 4K + its HDR.
        assert summary.resolution == "4K"
        assert summary.hdr is True

    async def test_get_many_omits_missing_ids(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        adapter = MediaLookupAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))
        summaries = await adapter.get_many(["mov_missing00000"], [], "en")

        assert summaries == {}

    async def test_get_many_handles_empty_input(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        adapter = MediaLookupAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))

        assert await adapter.get_many([], [], "en") == {}

    async def test_poster_path_is_none_when_media_has_none(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = MovieId.generate()
        await SQLAlchemyMovieRepository(db_session).save(_movie(movie_id, "No Poster"))
        await db_session.commit()

        adapter = MediaLookupAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))
        summaries = await adapter.get_many([str(movie_id)], [], "en")

        summary = summaries[(MediaType.MOVIE, str(movie_id))]
        assert summary.poster_path is None

    async def test_summaries_carry_the_minimum_age_of_movies_and_series(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        rated_movie = MovieId.generate()
        all_ages_movie = MovieId.generate()
        unrated_movie = MovieId.generate()
        rated_series = SeriesId.generate()
        await SQLAlchemyMovieRepository(db_session).save(
            _movie(rated_movie, "Rated", certification=_certification(16))
        )
        await SQLAlchemyMovieRepository(db_session).save(
            _movie(all_ages_movie, "All Ages", certification=_certification(0))
        )
        await SQLAlchemyMovieRepository(db_session).save(_movie(unrated_movie, "Unrated"))
        await SQLAlchemySeriesRepository(db_session).save(
            _series(rated_series, "Rated Show", certification=_certification(14))
        )
        await db_session.commit()

        adapter = MediaLookupAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))
        summaries = await adapter.get_many(
            [str(rated_movie), str(all_ages_movie), str(unrated_movie)], [str(rated_series)], "en"
        )

        assert summaries[(MediaType.MOVIE, str(rated_movie))].minimum_age == AgeRating(16)
        assert summaries[(MediaType.MOVIE, str(all_ages_movie))].minimum_age == AgeRating(0)
        assert summaries[(MediaType.MOVIE, str(unrated_movie))].minimum_age is None
        assert summaries[(MediaType.SERIES, str(rated_series))].minimum_age == AgeRating(14)

    async def test_age_without_a_label_reads_as_undetermined(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """An empty label is not a certification, whatever the age column holds."""
        now = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
        movie_id = "mov_rotulovazio1"
        series_id = "ser_rotulovazio1"
        async with session_factory() as session:
            session.add(
                MovieModel(
                    external_id=movie_id,
                    library_id=_LIBRARY_ID,
                    title="Empty Label",
                    year=2024,
                    duration=7200,
                    content_rating="",
                    minimum_age=12,
                    rating_system="br_dejus",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                SeriesModel(
                    external_id=series_id,
                    library_id=_LIBRARY_ID,
                    title="Empty Label Show",
                    start_year=2024,
                    content_rating="",
                    minimum_age=12,
                    rating_system="br_dejus",
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

        adapter = MediaLookupAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))
        summaries = await adapter.get_many([movie_id], [series_id], "en")

        assert summaries[(MediaType.MOVIE, movie_id)].minimum_age is None
        assert summaries[(MediaType.SERIES, series_id)].minimum_age is None

    async def test_titles_are_returned_whatever_their_library_or_age(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """No viewing policy at this layer: the use cases need hidden titles to tell them apart."""
        other_library = MovieId.generate()
        adult = MovieId.generate()
        await SQLAlchemyMovieRepository(db_session).save(
            _movie(
                other_library,
                "Other Shelf",
                library_id=_OTHER_LIBRARY_ID,
                certification=_certification(10),
            )
        )
        await SQLAlchemyMovieRepository(db_session).save(
            _movie(adult, "Adult", certification=_certification(18))
        )
        await db_session.commit()

        adapter = MediaLookupAdapter(SqlAlchemyMediaUnitOfWorkFactory(session_factory))
        summaries = await adapter.get_many([str(other_library), str(adult)], [], "en")

        assert summaries[(MediaType.MOVIE, str(other_library))].library_id == _OTHER_LIBRARY_ID
        assert summaries[(MediaType.MOVIE, str(adult))].minimum_age == AgeRating(18)
