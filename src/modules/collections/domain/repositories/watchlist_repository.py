"""Watchlist repository interface."""

from abc import ABC, abstractmethod

from src.modules.collections.domain.entities import WatchlistItem


class WatchlistRepository(ABC):
    """Abstract repository for WatchlistItem persistence.

    Example:
        >>> item = await repo.find_by_media_id("mov_abc123def456")
    """

    @abstractmethod
    async def find_by_media_id(self, media_id: str) -> WatchlistItem | None:
        """Find a watchlist item by media external ID.

        Args:
            media_id: External ID of the media (mov_xxx or ser_xxx).

        Returns:
            WatchlistItem if found, None otherwise.
        """

    @abstractmethod
    async def add(self, item: WatchlistItem) -> WatchlistItem:
        """Add an item to the watchlist.

        Args:
            item: The WatchlistItem entity to persist.

        Returns:
            The persisted WatchlistItem.
        """

    @abstractmethod
    async def remove(self, media_id: str) -> bool:
        """Soft-delete an item from the watchlist.

        Args:
            media_id: External ID of the media.

        Returns:
            True if removed, False if not found.
        """

    @abstractmethod
    async def list_all(self, limit: int = 100) -> list[WatchlistItem]:
        """List all watchlist items ordered by most recently added.

        Args:
            limit: Maximum number of items to return.

        Returns:
            List of WatchlistItem entities.
        """

    @abstractmethod
    async def exists(self, media_id: str) -> bool:
        """Check if a media item is in the watchlist.

        Args:
            media_id: External ID of the media.

        Returns:
            True if the item exists, False otherwise.
        """


__all__ = ["WatchlistRepository"]
