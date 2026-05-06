"""Library repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.value_objects.library_id import LibraryId


class LibraryRepository(ABC):
    """Repository interface for Library aggregate.

    This is a port in the hexagonal architecture pattern.
    Implementations (adapters) will be in the infrastructure layer.

    Example:
        >>> class SqlAlchemyLibraryRepository(LibraryRepository):
        ...     async def save(self, library: Library) -> Library:
        ...         # Persist to database
        ...         ...
    """

    @abstractmethod
    async def save(self, library: Library) -> Library:
        """Persist a library (create or update).

        Args:
            library: The library to save.

        Returns:
            The saved library (with generated ID if new).
        """
        ...

    @abstractmethod
    async def find_by_id(self, library_id: LibraryId) -> Library | None:
        """Find a library by its ID.

        Args:
            library_id: The library's external ID.

        Returns:
            The Library if found, None otherwise.
        """
        ...

    @abstractmethod
    async def find_all(self) -> Sequence[Library]:
        """Retrieve all libraries.

        Returns:
            Sequence of all libraries, may be empty.
        """
        ...

    @abstractmethod
    async def delete(self, library_id: LibraryId) -> bool:
        """Delete a library by its ID.

        Args:
            library_id: The library's external ID.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    async def exists(self, library_id: LibraryId) -> bool:
        """Check if a library exists.

        Args:
            library_id: The library's external ID.

        Returns:
            True if the library exists, False otherwise.
        """
        ...


__all__ = ["LibraryRepository"]
