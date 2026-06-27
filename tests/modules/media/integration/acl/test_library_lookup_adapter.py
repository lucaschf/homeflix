"""Integration tests for the Media LibraryLookupAdapter."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.library.domain.entities.library import Library
from src.modules.library.infrastructure.persistence.repositories.sqlalchemy_library_repository import (
    SqlAlchemyLibraryRepository,
)
from src.modules.library.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyLibraryUnitOfWorkFactory,
)
from src.modules.media.application.ports.library_lookup_port import LibraryRef
from src.modules.media.infrastructure.acl.library_lookup_adapter import LibraryLookupAdapter
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.library_id import LibraryId


def _make_adapter(
    session_factory: async_sessionmaker[AsyncSession],
) -> LibraryLookupAdapter:
    return LibraryLookupAdapter(SqlAlchemyLibraryUnitOfWorkFactory(session_factory))


@pytest.mark.integration
class TestLibraryLookupAdapter:
    """The adapter projects a Library to the consumer-owned LibraryRef."""

    async def test_find_returns_libraryref_with_id_and_paths(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        repo = SqlAlchemyLibraryRepository(db_session)
        saved = await repo.save(
            Library.create(name="Movies", library_type="movies", paths=["/movies", "/more"]),
        )
        await db_session.commit()

        adapter = _make_adapter(session_factory)
        ref = await adapter.find(str(saved.id))

        assert ref is not None
        assert ref == LibraryRef(
            id=str(saved.id),
            paths=(FilePath("/movies"), FilePath("/more")),
        )

    async def test_find_returns_none_for_missing_library(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        adapter = _make_adapter(session_factory)

        # Valid id shape, just not persisted → None (not an error).
        assert await adapter.find(str(LibraryId.generate())) is None
