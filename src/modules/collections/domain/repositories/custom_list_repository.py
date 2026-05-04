"""CustomList repository interface."""

from abc import ABC, abstractmethod

from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.shared_kernel.value_objects.profile_id import ProfileId


class CustomListRepository(ABC):
    """Abstract repository for CustomList persistence.

    Every read/delete method takes ``profile_id`` so a caller can never
    reach another profile's list — even with a known ``list_id``.
    ``add`` and ``update`` read the profile straight off the entity.

    Example:
        >>> lists = await repo.list_all(caller_profile_id)
        >>> items = await repo.list_items("lst_abc123def456", caller_profile_id)
    """

    # -- List CRUD -------------------------------------------------------------

    @abstractmethod
    async def find_by_id(
        self,
        list_id: str,
        profile_id: ProfileId,
    ) -> CustomList | None:
        """Find a list owned by ``profile_id`` with the given external ID."""

    @abstractmethod
    async def find_by_name(
        self,
        name: str,
        profile_id: ProfileId,
    ) -> CustomList | None:
        """Find a list (case-insensitive name match) within the profile."""

    @abstractmethod
    async def add(self, custom_list: CustomList) -> CustomList:
        """Persist a new custom list (profile is read from the entity)."""

    @abstractmethod
    async def update(self, custom_list: CustomList) -> CustomList:
        """Update an existing custom list (profile is read from the entity)."""

    @abstractmethod
    async def remove(self, list_id: str, profile_id: ProfileId) -> bool:
        """Soft-delete a list and its items, scoped to the profile."""

    @abstractmethod
    async def list_all(self, profile_id: ProfileId) -> list[CustomList]:
        """List the profile's custom lists, most recently updated first."""

    @abstractmethod
    async def count(self, profile_id: ProfileId) -> int:
        """Count active custom lists for the profile (for MAX_LISTS check)."""

    # -- Item management -------------------------------------------------------

    @abstractmethod
    async def find_item(
        self,
        list_id: str,
        media_id: str,
        profile_id: ProfileId,
    ) -> CustomListItem | None:
        """Find an item in a list, scoped to the profile owning that list."""

    @abstractmethod
    async def add_item(
        self,
        list_id: str,
        item: CustomListItem,
        profile_id: ProfileId,
    ) -> CustomListItem:
        """Persist an item under a list owned by ``profile_id``."""

    @abstractmethod
    async def remove_item(
        self,
        list_id: str,
        media_id: str,
        profile_id: ProfileId,
    ) -> bool:
        """Remove an item from a list owned by ``profile_id``."""

    @abstractmethod
    async def list_items(
        self,
        list_id: str,
        profile_id: ProfileId,
    ) -> list[CustomListItem]:
        """List items in a list owned by ``profile_id``, ordered by position."""

    @abstractmethod
    async def get_next_position(
        self,
        list_id: str,
        profile_id: ProfileId,
    ) -> int:
        """Return the next 0-based position to use for a new item."""


__all__ = ["CustomListRepository"]
