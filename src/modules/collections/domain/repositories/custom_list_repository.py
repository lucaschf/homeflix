"""CustomList repository interface."""

from abc import ABC, abstractmethod

from src.modules.collections.domain.entities import CustomList, CustomListItem


class CustomListRepository(ABC):
    """Abstract repository for CustomList persistence.

    Example:
        >>> lists = await repo.list_all()
        >>> items = await repo.list_items("lst_abc123def456")
    """

    # -- List CRUD -------------------------------------------------------------

    @abstractmethod
    async def find_by_id(self, list_id: str) -> CustomList | None:
        """Find a custom list by its external ID.

        Args:
            list_id: External ID of the list (lst_xxx).

        Returns:
            CustomList if found, None otherwise.
        """

    @abstractmethod
    async def find_by_name(self, name: str) -> CustomList | None:
        """Find a custom list by name (case-insensitive).

        Args:
            name: Name of the list.

        Returns:
            CustomList if found, None otherwise.
        """

    @abstractmethod
    async def add(self, custom_list: CustomList) -> CustomList:
        """Persist a new custom list.

        Args:
            custom_list: The CustomList entity to persist.

        Returns:
            The persisted CustomList.
        """

    @abstractmethod
    async def update(self, custom_list: CustomList) -> CustomList:
        """Update an existing custom list.

        Args:
            custom_list: The CustomList entity with updates.

        Returns:
            The updated CustomList.
        """

    @abstractmethod
    async def remove(self, list_id: str) -> bool:
        """Soft-delete a custom list and all its items.

        Args:
            list_id: External ID of the list.

        Returns:
            True if removed, False if not found.
        """

    @abstractmethod
    async def list_all(self) -> list[CustomList]:
        """List all custom lists ordered by most recently updated.

        Returns:
            List of CustomList entities.
        """

    @abstractmethod
    async def count(self) -> int:
        """Count total active custom lists.

        Returns:
            Number of non-deleted custom lists.
        """

    # -- Item management -------------------------------------------------------

    @abstractmethod
    async def find_item(self, list_id: str, media_id: str) -> CustomListItem | None:
        """Find an item in a custom list.

        Args:
            list_id: External ID of the list.
            media_id: External ID of the media.

        Returns:
            CustomListItem if found, None otherwise.
        """

    @abstractmethod
    async def add_item(self, list_id: str, item: CustomListItem) -> CustomListItem:
        """Add an item to a custom list.

        Args:
            list_id: External ID of the list.
            item: The CustomListItem entity to persist.

        Returns:
            The persisted CustomListItem.
        """

    @abstractmethod
    async def remove_item(self, list_id: str, media_id: str) -> bool:
        """Remove an item from a custom list.

        Args:
            list_id: External ID of the list.
            media_id: External ID of the media.

        Returns:
            True if removed, False if not found.
        """

    @abstractmethod
    async def list_items(self, list_id: str) -> list[CustomListItem]:
        """List all items in a custom list ordered by position.

        Args:
            list_id: External ID of the list.

        Returns:
            List of CustomListItem entities.
        """


__all__ = ["CustomListRepository"]
