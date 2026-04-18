"""ToggleWatchlistUseCase - Add or remove an item from the watchlist."""

from src.modules.collections.application.dtos import (
    ToggleWatchlistInput,
    ToggleWatchlistOutput,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.entities import WatchlistItem


class ToggleWatchlistUseCase:
    """Toggle a media item in the user's watchlist.

    If the item is already in the watchlist, it is removed.
    If it is not in the watchlist, it is added.

    Example:
        >>> use_case = ToggleWatchlistUseCase(uow_factory)
        >>> result = await use_case.execute(ToggleWatchlistInput(
        ...     media_id="mov_abc123def456",
        ...     media_type="movie",
        ... ))
        >>> result.added
        True
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ToggleWatchlistInput) -> ToggleWatchlistOutput:
        """Execute the use case.

        Args:
            input_dto: Contains media_id and media_type.

        Returns:
            ToggleWatchlistOutput with added=True if added, False if removed.
        """
        async with self._uow_factory() as uow:
            exists = await uow.watchlist.exists(input_dto.media_id)

            if exists:
                await uow.watchlist.remove(input_dto.media_id)
                return ToggleWatchlistOutput(media_id=input_dto.media_id, added=False)

            item = WatchlistItem.create(
                media_id=input_dto.media_id,
                media_type=input_dto.media_type,
            )
            await uow.watchlist.add(item)
            return ToggleWatchlistOutput(media_id=input_dto.media_id, added=True)


__all__ = ["ToggleWatchlistUseCase"]
