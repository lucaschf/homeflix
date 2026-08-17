"""Integration tests for SqlAlchemyLibraryRepository.

Exercises the repository against a real (in-memory SQLite) session,
covering the paths the unit-level mocks cannot: id generation on save,
upsert of an existing row (no duplicate), the restore-on-save branch for
a soft-deleted row, and the soft-delete-aware query methods.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.value_objects.library_type import LibraryType
from src.modules.library.infrastructure.persistence.models.library_model import (
    LibraryModel,
)
from src.modules.library.infrastructure.persistence.repositories.sqlalchemy_library_repository import (
    SqlAlchemyLibraryRepository,
)
from src.shared_kernel.value_objects.library_id import LibraryId

pytestmark = pytest.mark.integration


def _make_library(
    name: str = "Movies",
    library_type: LibraryType = LibraryType.MOVIES,
    path: str = "/media/movies",
    library_id: LibraryId | None = None,
) -> Library:
    """Build a Library entity for persistence tests.

    When ``library_id`` is omitted the entity is constructed with
    ``id=None`` so ``save`` exercises the generate-if-absent branch.
    """
    return Library(
        id=library_id,
        name=name,
        library_type=library_type,
        paths=[path],
    )


async def _row_count(session: AsyncSession) -> int:
    """Count every library row, including soft-deleted ones."""
    result = await session.execute(select(func.count()).select_from(LibraryModel))
    return int(result.scalar_one())


class TestSave:
    async def test_assigns_id_when_absent_and_round_trips_fields(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyLibraryRepository(session)

            saved = await repo.save(_make_library(name="Anime", path="/media/anime"))
            await session.commit()

            assert saved.id is not None
            assert str(saved.id).startswith("lib_")
            assert saved.name.value == "Anime"
            assert [p.value for p in saved.paths] == ["/media/anime"]

    async def test_preserves_explicit_id(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        explicit = LibraryId.generate()
        async with session_factory() as session:
            repo = SqlAlchemyLibraryRepository(session)

            saved = await repo.save(_make_library(library_id=explicit))
            await session.commit()

            assert saved.id == explicit

    async def test_upsert_updates_in_place_without_duplicating_row(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyLibraryRepository(session)
            first = await repo.save(_make_library(name="Films"))
            await session.commit()
            assert first.id is not None

            renamed = first.with_updates(name="Cinema")
            updated = await repo.save(renamed)
            await session.commit()

            assert updated.id == first.id
            assert updated.name.value == "Cinema"
            assert await _row_count(session) == 1

    async def test_restores_soft_deleted_row_on_save(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyLibraryRepository(session)
            original = await repo.save(_make_library(name="Docs"))
            await session.commit()
            assert original.id is not None

            assert await repo.delete(original.id) is True
            await session.commit()
            assert await repo.find_by_id(original.id) is None

            revived = await repo.save(original.with_updates(name="Documentaries"))
            await session.commit()

            assert revived.id == original.id
            assert revived.name.value == "Documentaries"
            # Restored in place — the soft-delete tombstone is reused,
            # never a second row for the same external id.
            assert await _row_count(session) == 1
            assert await repo.find_by_id(original.id) is not None


class TestQueries:
    async def test_find_by_id_returns_none_for_unknown(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyLibraryRepository(session)
            assert await repo.find_by_id(LibraryId.generate()) is None

    async def test_find_all_orders_by_name_and_excludes_deleted(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyLibraryRepository(session)
            await repo.save(_make_library(name="Zed", path="/z"))
            await repo.save(_make_library(name="Alpha", path="/a"))
            doomed = await repo.save(_make_library(name="Mid", path="/m"))
            await session.commit()
            assert doomed.id is not None
            await repo.delete(doomed.id)
            await session.commit()

            names = [lib.name.value for lib in await repo.find_all()]

            assert names == ["Alpha", "Zed"]


class TestDeleteAndExists:
    async def test_delete_is_idempotent_and_reports_outcome(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyLibraryRepository(session)
            lib = await repo.save(_make_library())
            await session.commit()
            assert lib.id is not None

            assert await repo.delete(lib.id) is True
            await session.commit()
            # Second delete: already a tombstone → nothing to soft-delete.
            assert await repo.delete(lib.id) is False
            assert await repo.delete(LibraryId.generate()) is False

    async def test_exists_reflects_live_and_deleted_state(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyLibraryRepository(session)
            lib = await repo.save(_make_library())
            await session.commit()
            assert lib.id is not None

            assert await repo.exists(lib.id) is True
            await repo.delete(lib.id)
            await session.commit()
            assert await repo.exists(lib.id) is False
            assert await repo.exists(LibraryId.generate()) is False
