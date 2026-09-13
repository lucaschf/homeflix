"""ToggleWatchlistUseCase - Add or remove an item from the watchlist."""

from src.modules.collections.application.dtos import (
    ToggleWatchlistInput,
    ToggleWatchlistOutput,
)
from src.modules.collections.application.ports import (
    MediaLookupPort,
    ProfileViewingPolicyPort,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.application.use_cases._title_gate import (
    is_title_visible,
    title_not_found,
    title_of,
)
from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


class ToggleWatchlistUseCase:
    """Toggle a media item in the caller's watchlist.

    If the item is already in the profile's watchlist, it is removed.
    If it is not, it is added.

    Only a title the profile can see is added. Removal is never gated:
    the toggle is the watchlist's only way out, so an entry whose title
    became hidden — or never was reachable — must still be removable.
    The policy and the title's visibility are read before the watchlist
    transaction opens, so no collections transaction is held while
    Identity and Media answer.
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

    async def execute(self, input_dto: ToggleWatchlistInput) -> ToggleWatchlistOutput:
        """Toggle the entry, scoped to the caller's profile.

        Raises:
            ResourceNotFoundException: If the entry is absent and the
                movie or series does not exist or the profile cannot see
                it — the two cases raise the same error, and nothing is
                saved.
        """
        profile_id = ProfileId(input_dto.profile_id)
        media_id = CollectionMediaId(input_dto.media_id)

        title = title_of(media_id)
        policy = await self._profile_viewing_policy.find_for_profile(profile_id)
        visible = await is_title_visible(self._media_lookup, title, policy)

        async with self._uow_factory() as uow:
            exists = await uow.watchlist.exists(media_id, profile_id)

            if exists:
                await uow.watchlist.remove(media_id, profile_id)
                return ToggleWatchlistOutput(media_id=input_dto.media_id, added=False)

            if not visible:
                raise title_not_found(title)

            item = WatchlistItem.create(
                profile_id=profile_id,
                media_id=media_id,
                media_type=input_dto.media_type,
            )
            await uow.watchlist.add(item)
            return ToggleWatchlistOutput(media_id=input_dto.media_id, added=True)


__all__ = ["ToggleWatchlistUseCase"]
