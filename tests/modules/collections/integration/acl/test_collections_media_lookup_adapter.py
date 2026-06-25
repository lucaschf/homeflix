"""Integration tests for the Collections MediaLookupAdapter."""

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
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)
from src.shared_kernel.value_objects import MediaType

_LIBRARY_ID = "lib_test12345678"


def _movie(movie_id: MovieId, title: str, poster: str | None = None) -> Movie:
    return Movie(
        library_id=_LIBRARY_ID,
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
    )


def _series(series_id: SeriesId, title: str, poster: str | None = None) -> Series:
    return Series(
        library_id=_LIBRARY_ID,
        id=series_id,
        title=Title(title),
        start_year=Year(2024),
        poster_path=ImageUrl(poster) if poster else None,
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
