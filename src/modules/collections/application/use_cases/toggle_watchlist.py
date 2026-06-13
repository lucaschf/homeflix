"""ToggleWatchlistUseCase - Add or remove an item from the watchlist."""

from src.modules.collections.application.dtos import (
    ToggleWatchlistInput,
    ToggleWatchlistOutput,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


class ToggleWatchlistUseCase:
    """Toggle a media item in the caller's watchlist.

    If the item is already in the profile's watchlist, it is removed.
    If it is not, it is added.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ToggleWatchlistInput) -> ToggleWatchlistOutput:
        """Toggle the entry, scoped to the caller's profile."""
        profile_id = ProfileId(input_dto.profile_id)
        media_id = CollectionMediaId(input_dto.media_id)
        async with self._uow_factory() as uow:
            exists = await uow.watchlist.exists(media_id, profile_id)

            if exists:
                await uow.watchlist.remove(media_id, profile_id)
                return ToggleWatchlistOutput(media_id=input_dto.media_id, added=False)

            item = WatchlistItem.create(
                profile_id=profile_id,
                media_id=media_id,
                media_type=input_dto.media_type,
            )
            await uow.watchlist.add(item)
            return ToggleWatchlistOutput(media_id=input_dto.media_id, added=True)


__all__ = ["ToggleWatchlistUseCase"]
