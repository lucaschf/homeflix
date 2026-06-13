"""CheckWatchlistUseCase - Check if a media item is in the watchlist."""

from src.modules.collections.application.dtos import CheckWatchlistInput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


class CheckWatchlistUseCase:
    """Check whether a media item is in the caller's watchlist."""

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: CheckWatchlistInput) -> bool:
        """Return True if the profile has the item on its watchlist."""
        async with self._uow_factory() as uow:
            return await uow.watchlist.exists(
                CollectionMediaId(input_dto.media_id), ProfileId(input_dto.profile_id)
            )


__all__ = ["CheckWatchlistUseCase"]
