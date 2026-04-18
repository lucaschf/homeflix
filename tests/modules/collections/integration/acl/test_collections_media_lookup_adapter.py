"""Integration tests for the Collections MediaLookupAdapter."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.infrastructure.acl import MediaLookupAdapter
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
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
from src.shared_kernel.value_objects import CollectionMediaType


def _movie(movie_id: MovieId, title: str, poster: str | None = None) -> Movie:
    return Movie(
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
        id=series_id,
        title=Title(title),
        start_year=Year(2024),
        poster_path=ImageUrl(poster) if poster else None,
    )


@pytest.mark.integration
class TestCollectionsMediaLookupAdapter:
    """The adapter resolves titles + posters for the Collections BC."""

    async def test_get_many_resolves_movies_and_series(self, db_session: AsyncSession) -> None:
        movie_repo = SQLAlchemyMovieRepository(db_session)
        series_repo = SQLAlchemySeriesRepository(db_session)

        movie_id = MovieId.generate()
        series_id = SeriesId.generate()
        await movie_repo.save(_movie(movie_id, "Inception", "/p/inception.jpg"))
        await series_repo.save(_series(series_id, "Breaking Bad", "/p/bb.jpg"))

        adapter = MediaLookupAdapter(movie_repo, series_repo)

        summaries = await adapter.get_many([str(movie_id)], [str(series_id)], "en")

        movie_summary = summaries[(CollectionMediaType.MOVIE, str(movie_id))]
        assert movie_summary.title == "Inception"
        assert movie_summary.poster_path == "/p/inception.jpg"

        series_summary = summaries[(CollectionMediaType.SERIES, str(series_id))]
        assert series_summary.title == "Breaking Bad"
        assert series_summary.poster_path == "/p/bb.jpg"

    async def test_get_many_omits_missing_ids(self, db_session: AsyncSession) -> None:
        movie_repo = SQLAlchemyMovieRepository(db_session)
        series_repo = SQLAlchemySeriesRepository(db_session)

        adapter = MediaLookupAdapter(movie_repo, series_repo)
        summaries = await adapter.get_many(["mov_missing00000"], [], "en")

        assert summaries == {}

    async def test_get_many_handles_empty_input(self, db_session: AsyncSession) -> None:
        movie_repo = SQLAlchemyMovieRepository(db_session)
        series_repo = SQLAlchemySeriesRepository(db_session)
        adapter = MediaLookupAdapter(movie_repo, series_repo)

        assert await adapter.get_many([], [], "en") == {}

    async def test_poster_path_is_none_when_media_has_none(self, db_session: AsyncSession) -> None:
        movie_repo = SQLAlchemyMovieRepository(db_session)
        series_repo = SQLAlchemySeriesRepository(db_session)

        movie_id = MovieId.generate()
        await movie_repo.save(_movie(movie_id, "No Poster"))

        adapter = MediaLookupAdapter(movie_repo, series_repo)
        summaries = await adapter.get_many([str(movie_id)], [], "en")

        summary = summaries[(CollectionMediaType.MOVIE, str(movie_id))]
        assert summary.poster_path is None
