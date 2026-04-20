"""CheckWatchlistUseCase - Check if a media item is in the watchlist."""

from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory


class CheckWatchlistUseCase:
    """Check whether a media item exists in the user's watchlist.

    Example:
        >>> use_case = CheckWatchlistUseCase(uow_factory)
        >>> in_list = await use_case.execute("mov_abc123def456")
        >>> in_list
        True
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, media_id: str) -> bool:
        """Execute the use case.

        Args:
            media_id: External ID of the media to check.

        Returns:
            True if the item is in the watchlist, False otherwise.
        """
        async with self._uow_factory() as uow:
            return await uow.watchlist.exists(media_id)


__all__ = ["CheckWatchlistUseCase"]
