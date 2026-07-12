"""Integration tests for the partial-unique index on media_files.file_path.

``media_files.file_path`` is unique only among live rows
(``deleted_at IS NULL``), mirroring movies/episodes. A soft-deleted variant
keeps its path (audit/undo) but must not block a live row from taking the
same path — while two *live* rows with the same path stay forbidden.

The tests operate directly on ``media_files`` (rather than via two Movies)
so they isolate the media_files index, without tripping the separate
partial-unique index on the denormalized ``movies.file_path`` column.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.models import MediaFileModel, MovieModel
from src.modules.media.infrastructure.persistence.repositories import SQLAlchemyMovieRepository

_LIBRARY_ID = "lib_test12345678"
_PATH = "/movies/variant.mkv"


def _movie(title: str, file_path: str) -> Movie:
    """Build a Movie with a single primary file variant at *file_path*."""
    return Movie(
        library_id=_LIBRARY_ID,
        id=MovieId.generate(),
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(file_path),
                file_size=1_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


def _variant(movie_id: int, external_id: str) -> MediaFileModel:
    """Build a live media_file variant row on *movie_id* sharing ``_PATH``."""
    return MediaFileModel(
        movie_id=movie_id,
        file_path=_PATH,
        file_size=2_000_000,
        resolution_width=1920,
        resolution_height=1080,
        resolution_name="1080p",
        is_primary=False,
        added_at=datetime(2026, 7, 12, tzinfo=UTC),
        external_id=external_id,
    )


async def _seed_movie_id(db_session: AsyncSession) -> int:
    """Persist a movie whose primary variant already holds ``_PATH``."""
    await SQLAlchemyMovieRepository(db_session).save(_movie("Owner", _PATH))
    row = await db_session.execute(
        select(MovieModel.id).where(MovieModel.library_id == _LIBRARY_ID)
    )
    return row.scalar_one()


@pytest.mark.integration
class TestMediaFilePartialUniqueFilePath:
    """Uniqueness of media_files.file_path is scoped to live rows."""

    async def test_reuses_path_once_the_holder_is_soft_deleted(
        self, db_session: AsyncSession
    ) -> None:
        # A soft-deleted variant must not lock its path: a fresh live row can
        # take it. Before the index was made partial this raised IntegrityError.
        movie_id = await _seed_movie_id(db_session)
        await db_session.execute(
            update(MediaFileModel)
            .where(MediaFileModel.file_path == _PATH)
            .values(deleted_at=datetime(2026, 7, 12, tzinfo=UTC))
        )

        db_session.add(_variant(movie_id, "mfl_reuseafterdel"))
        await db_session.flush()  # must not raise

        live = await db_session.execute(
            select(MediaFileModel).where(
                MediaFileModel.file_path == _PATH,
                MediaFileModel.deleted_at.is_(None),
            )
        )
        assert len(live.scalars().all()) == 1

    async def test_rejects_two_live_rows_with_same_path(self, db_session: AsyncSession) -> None:
        movie_id = await _seed_movie_id(db_session)  # already holds _PATH (live)

        db_session.add(_variant(movie_id, "mfl_secondlive"))
        with pytest.raises(IntegrityError):
            await db_session.flush()
