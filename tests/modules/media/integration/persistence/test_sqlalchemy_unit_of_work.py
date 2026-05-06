"""Integration tests for SqlAlchemyMediaUnitOfWork.

Exercises the real commit/rollback behaviour against an in-memory
SQLite database so the contract under production SQLAlchemy semantics
is covered.
"""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.persistence import Base
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
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWork,
    SqlAlchemyMediaUnitOfWorkFactory,
)

_LIBRARY_ID = "lib_test12345678"


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Build a dedicated in-memory engine and session factory per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    yield factory

    await engine.dispose()


def _movie(title: str = "Inception") -> Movie:
    return Movie(
        library_id=_LIBRARY_ID,
        id=MovieId.generate(),
        title=Title(title),
        year=Year(2010),
        duration=Duration(8880),
        files=[
            MediaFile(
                file_path=FilePath(f"/movies/{title.lower()}.mkv"),
                file_size=1_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


@pytest.mark.integration
class TestSqlAlchemyMediaUnitOfWork:
    """Commit/rollback semantics under SQLAlchemy."""

    async def test_should_commit_on_clean_exit(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        uow = SqlAlchemyMediaUnitOfWork(session_factory)
        movie = _movie("Arrival")

        async with uow as active:
            await active.movies.save(movie)

        # A fresh UoW should see the committed row.
        async with SqlAlchemyMediaUnitOfWork(session_factory) as reader:
            assert movie.id is not None
            found = await reader.movies.find_by_id(movie.id)
            assert found is not None
            assert found.title.value == "Arrival"

    async def test_should_rollback_on_exception(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        uow = SqlAlchemyMediaUnitOfWork(session_factory)
        movie = _movie("Tenet")

        with pytest.raises(RuntimeError, match="boom"):
            async with uow as active:
                await active.movies.save(movie)
                raise RuntimeError("boom")

        async with SqlAlchemyMediaUnitOfWork(session_factory) as reader:
            assert movie.id is not None
            found = await reader.movies.find_by_id(movie.id)
            assert found is None

    async def test_should_reject_nested_enter(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        uow = SqlAlchemyMediaUnitOfWork(session_factory)

        async with uow:
            with pytest.raises(RuntimeError, match="already active"):
                await uow.__aenter__()

    async def test_should_allow_reuse_across_transactions(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        uow = SqlAlchemyMediaUnitOfWork(session_factory)

        first = _movie("First")
        second = _movie("Second")

        async with uow as active:
            await active.movies.save(first)
        async with uow as active:
            await active.movies.save(second)

        async with SqlAlchemyMediaUnitOfWork(session_factory) as reader:
            assert first.id is not None and second.id is not None
            assert await reader.movies.find_by_id(first.id) is not None
            assert await reader.movies.find_by_id(second.id) is not None

    async def test_factory_should_produce_fresh_instances(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        factory = SqlAlchemyMediaUnitOfWorkFactory(session_factory)

        uow1 = factory()
        uow2 = factory()

        assert uow1 is not uow2

    async def test_factory_uows_should_isolate_failures(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """A failure inside one UoW must not roll back a sibling UoW's commit."""
        factory = SqlAlchemyMediaUnitOfWorkFactory(session_factory)
        ok_movie = _movie("Ok")
        bad_movie = _movie("Bad")

        async with factory() as uow:
            await uow.movies.save(ok_movie)

        with pytest.raises(RuntimeError, match="boom"):
            async with factory() as uow:
                await uow.movies.save(bad_movie)
                raise RuntimeError("boom")

        async with factory() as reader:
            assert ok_movie.id is not None and bad_movie.id is not None
            assert await reader.movies.find_by_id(ok_movie.id) is not None
            assert await reader.movies.find_by_id(bad_movie.id) is None
