"""CheckWatchlistUseCase - Check if a media item is in the watchlist."""

from src.modules.collections.application.dtos import CheckWatchlistInput
from src.modules.collections.application.ports import (
    MediaLookupPort,
    ProfileViewingPolicyPort,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.application.use_cases._title_gate import (
    is_title_visible,
    title_of,
)
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


class CheckWatchlistUseCase:
    """Check whether a media item is in the caller's watchlist.

    An entry on a title the profile can no longer see is answered as
    absent, the same way the watchlist read drops it, so the check
    reveals nothing the list itself hides.
    """

    def __init__(
        self,
        uow_factory: CollectionsUnitOfWorkFactory,
        media_lookup: MediaLookupPort,
        profile_viewing_policy: ProfileViewingPolicyPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
            media_lookup: Port for asking the catalog which titles are visible.
            profile_viewing_policy: Port resolving the caller's viewing policy.
        """
        self._uow_factory = uow_factory
        self._media_lookup = media_lookup
        self._profile_viewing_policy = profile_viewing_policy

    async def execute(self, input_dto: CheckWatchlistInput) -> bool:
        """Return True if the profile has the item on its watchlist and can see it."""
        profile_id = ProfileId(input_dto.profile_id)
        media_id = CollectionMediaId(input_dto.media_id)
        async with self._uow_factory() as uow:
            exists = await uow.watchlist.exists(media_id, profile_id)
        if not exists:
            return False

        policy = await self._profile_viewing_policy.find_for_profile(profile_id)
        return await is_title_visible(self._media_lookup, title_of(media_id), policy)


__all__ = ["CheckWatchlistUseCase"]
