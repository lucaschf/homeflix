"""ToggleWatchlistUseCase - Add or remove an item from the watchlist."""

from src.modules.collections.application.dtos import (
    ToggleWatchlistInput,
    ToggleWatchlistOutput,
)
from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.repositories import WatchlistRepository


class ToggleWatchlistUseCase:
    """Toggle a media item in the user's watchlist.

    If the item is already in the watchlist, it is removed.
    If it is not in the watchlist, it is added.

    Example:
        >>> use_case = ToggleWatchlistUseCase(watchlist_repository)
        >>> result = await use_case.execute(ToggleWatchlistInput(
        ...     media_id="mov_abc123def456",
        ...     media_type="movie",
        ... ))
        >>> result.added
        True
    """

    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        """Initialize the use case.

        Args:
            watchlist_repository: Repository for watchlist persistence.
        """
        self._repo = watchlist_repository

    async def execute(self, input_dto: ToggleWatchlistInput) -> ToggleWatchlistOutput:
        """Execute the use case.

        Args:
            input_dto: Contains media_id and media_type.

        Returns:
            ToggleWatchlistOutput with added=True if added, False if removed.
        """
        exists = await self._repo.exists(input_dto.media_id)

        if exists:
            await self._repo.remove(input_dto.media_id)
            return ToggleWatchlistOutput(media_id=input_dto.media_id, added=False)

        item = WatchlistItem.create(
            media_id=input_dto.media_id,
            media_type=input_dto.media_type,
        )
        await self._repo.add(item)
        return ToggleWatchlistOutput(media_id=input_dto.media_id, added=True)


__all__ = ["ToggleWatchlistUseCase"]
