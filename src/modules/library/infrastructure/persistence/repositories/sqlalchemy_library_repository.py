"""SQLAlchemy implementation of LibraryRepository."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.repositories.library_repository import LibraryRepository
from src.modules.library.domain.value_objects.library_id import LibraryId
from src.modules.library.infrastructure.persistence.mappers.library_mapper import LibraryMapper
from src.modules.library.infrastructure.persistence.models.library_model import LibraryModel


class SqlAlchemyLibraryRepository(LibraryRepository):
    """Async SQLAlchemy repository for Library aggregates.

    Follows the same patterns as ``SQLAlchemyMovieRepository``:
    soft-delete, flush + commit per write, reload after save.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, library: Library) -> Library:
        """Persist a library (create or update).

        Generates an external id if the entity doesn't have one yet.
        On update, field values from the entity overwrite the model;
        the mapper never touches base columns (id, created_at, etc.).

        Args:
            library: The Library to persist.

        Returns:
            The saved Library, re-read from the DB so the caller sees
            any server-generated values (timestamps, auto-increment id).
        """
        library = library.with_updates(
            id=LibraryId.generate_if_absent(library.id),
        )

        stmt = select(LibraryModel).where(
            LibraryModel.external_id == str(library.id),
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None and existing.is_deleted:
            existing.restore()

        if existing is not None:
            LibraryMapper.update_model(existing, library)
            await self._session.flush()
        else:
            model = LibraryMapper.to_model(library)
            self._session.add(model)
            await self._session.flush()

        await self._session.commit()

        assert library.id is not None
        saved = await self.find_by_id(library.id)
        assert saved is not None
        return saved

    async def find_by_id(self, library_id: LibraryId) -> Library | None:
        """Find a library by its external id.

        Args:
            library_id: The library's external id (``lib_xxx``).

        Returns:
            The Library if found and not soft-deleted, ``None`` otherwise.
        """
        stmt = select(LibraryModel).where(
            LibraryModel.external_id == str(library_id),
            LibraryModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else LibraryMapper.to_entity(model)

    async def find_all(self) -> Sequence[Library]:
        """List all non-deleted libraries ordered by name.

        Returns:
            Sequence of libraries (may be empty).
        """
        stmt = (
            select(LibraryModel)
            .where(LibraryModel.deleted_at.is_(None))
            .order_by(LibraryModel.name)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [LibraryMapper.to_entity(m) for m in models]

    async def delete(self, library_id: LibraryId) -> bool:
        """Soft-delete a library.

        Args:
            library_id: The library's external id.

        Returns:
            ``True`` if the library was found and deleted, ``False``
            if it didn't exist or was already deleted.
        """
        stmt = select(LibraryModel).where(
            LibraryModel.external_id == str(library_id),
            LibraryModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        model.soft_delete()
        await self._session.flush()
        await self._session.commit()
        return True

    async def exists(self, library_id: LibraryId) -> bool:
        """Check whether a non-deleted library with this id exists.

        Args:
            library_id: The library's external id.

        Returns:
            ``True`` if found and not soft-deleted.
        """
        stmt = select(LibraryModel.id).where(
            LibraryModel.external_id == str(library_id),
            LibraryModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None


__all__ = ["SqlAlchemyLibraryRepository"]
