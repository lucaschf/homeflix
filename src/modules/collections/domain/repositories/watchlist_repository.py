"""Watchlist repository interface."""

from abc import ABC, abstractmethod

from src.modules.collections.domain.entities import WatchlistItem
from src.shared_kernel.value_objects.profile_id import ProfileId


class WatchlistRepository(ABC):
    """Abstract repository for ``WatchlistItem`` persistence.

    Every read/delete operation takes ``profile_id`` so a profile only
    sees its own watchlist. ``add`` reads the profile from the entity.

    Example:
        >>> item = await repo.find_by_media_id(
        ...     "mov_abc123def456", caller_profile_id
        ... )
    """

    @abstractmethod
    async def find_by_media_id(
        self,
        media_id: str,
        profile_id: ProfileId,
    ) -> WatchlistItem | None:
        """Find an entry for ``media_id`` in ``profile_id``'s watchlist."""

    @abstractmethod
    async def add(self, item: WatchlistItem) -> WatchlistItem:
        """Add an item (profile is read from the entity)."""

    @abstractmethod
    async def remove(self, media_id: str, profile_id: ProfileId) -> bool:
        """Soft-delete an item from ``profile_id``'s watchlist."""

    @abstractmethod
    async def list_all(
        self,
        profile_id: ProfileId,
        limit: int = 100,
    ) -> list[WatchlistItem]:
        """List the profile's watchlist items, most recently added first."""

    @abstractmethod
    async def exists(self, media_id: str, profile_id: ProfileId) -> bool:
        """Check whether ``media_id`` is on ``profile_id``'s watchlist."""


__all__ = ["WatchlistRepository"]
