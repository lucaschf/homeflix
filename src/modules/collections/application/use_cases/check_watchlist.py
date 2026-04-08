"""CheckWatchlistUseCase - Check if a media item is in the watchlist."""

from src.modules.collections.domain.repositories import WatchlistRepository


class CheckWatchlistUseCase:
    """Check whether a media item exists in the user's watchlist.

    Example:
        >>> use_case = CheckWatchlistUseCase(watchlist_repository)
        >>> in_list = await use_case.execute("mov_abc123def456")
        >>> in_list
        True
    """

    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        """Initialize the use case.

        Args:
            watchlist_repository: Repository for watchlist persistence.
        """
        self._repo = watchlist_repository

    async def execute(self, media_id: str) -> bool:
        """Execute the use case.

        Args:
            media_id: External ID of the media to check.

        Returns:
            True if the item is in the watchlist, False otherwise.
        """
        return await self._repo.exists(media_id)


__all__ = ["CheckWatchlistUseCase"]
