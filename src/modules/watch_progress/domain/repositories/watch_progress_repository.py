"""WatchProgress repository interface."""

from abc import ABC, abstractmethod

from src.modules.watch_progress.domain.entities import WatchProgress


class WatchProgressRepository(ABC):
    """Abstract repository for WatchProgress persistence.

    Example:
        >>> progress = await repo.find_by_media_id("mov_abc123def456")
    """

    @abstractmethod
    async def find_by_media_id(self, media_id: str) -> WatchProgress | None:
        """Find progress by media external ID.

        Args:
            media_id: External ID of the media (mov_xxx or epi_xxx).

        Returns:
            WatchProgress if found, None otherwise.
        """

    @abstractmethod
    async def save(self, progress: WatchProgress) -> WatchProgress:
        """Create or update a watch progress record.

        Args:
            progress: The WatchProgress entity to persist.

        Returns:
            The persisted WatchProgress.
        """

    @abstractmethod
    async def list_in_progress(self, limit: int = 20) -> list[WatchProgress]:
        """List in-progress items ordered by last watched (most recent first).

        Args:
            limit: Maximum number of items to return.

        Returns:
            List of WatchProgress with status "in_progress".
        """

    @abstractmethod
    async def find_by_media_ids(self, media_ids: list[str]) -> dict[str, WatchProgress]:
        """Find progress for multiple media items in a single query.

        Args:
            media_ids: List of external media IDs.

        Returns:
            Dict mapping media_id to WatchProgress for found records.
        """

    @abstractmethod
    async def delete(self, media_id: str) -> bool:
        """Soft-delete progress for a media item.

        Args:
            media_id: External ID of the media.

        Returns:
            True if deleted, False if not found.
        """


__all__ = ["WatchProgressRepository"]
