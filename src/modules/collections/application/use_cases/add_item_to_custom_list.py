"""AddItemToCustomListUseCase - Add a media item to a custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import AddItemToCustomListInput
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
from src.modules.collections.domain.entities import CustomListItem
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


class AddItemToCustomListUseCase:
    """Add a movie or series to a custom list owned by the caller's profile.

    Enforces the per-list item limit and prevents duplicates within the
    list. Only a title the profile can see is added.

    The checks run in a fixed order, and the first one that fails
    decides the response:

    1. The list is not the caller's: 404 for the list — whatever the
       title, so another profile's list cannot be used to probe titles.
    2. The title does not exist or the profile cannot see it: 404 for
       the title, the same for both cases.
    3. The title is already in the list: duplicate.
    4. The list is full: limit exceeded.

    The title's visibility is read before the list transaction opens, so
    no collections transaction is held while Identity and Media answer;
    it is only acted on once the list is known to be the caller's.
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

    async def execute(self, input_dto: AddItemToCustomListInput) -> None:
        """Add the item, enforcing list ownership, visibility and limits.

        Raises:
            ResourceNotFoundException: If the list is not the caller's, or
                if the movie or series does not exist or the profile
                cannot see it — the last two raise the same error.
            BusinessRuleViolationException: If the title is already in the
                list, or the list is full.
        """
        profile_id = ProfileId(input_dto.profile_id)
        media_id = CollectionMediaId(input_dto.media_id)

        title = title_of(media_id)
        policy = await self._profile_viewing_policy.find_for_profile(profile_id)
        visible = await is_title_visible(self._media_lookup, title, policy)

        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id, profile_id)
            if not custom_list:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            if not visible:
                raise title_not_found(title)

            existing_item = await uow.custom_lists.find_item(
                input_dto.list_id, media_id, profile_id
            )
            if existing_item:
                raise BusinessRuleViolationException(
                    message="Item already exists in this list",
                    message_code="CUSTOM_LIST_ITEM_DUPLICATE",
                    rule_code="CUSTOM_LIST_ITEM_DUPLICATE",
                )

            # Validate item limit via domain entity
            updated_list = custom_list.increment_item_count()

            next_position = await uow.custom_lists.get_next_position(input_dto.list_id, profile_id)

            item = CustomListItem.create(
                media_id=media_id,
                media_type=input_dto.media_type,
                position=next_position,
            )

            await uow.custom_lists.add_item(input_dto.list_id, item, profile_id)
            await uow.custom_lists.update(updated_list)


__all__ = ["AddItemToCustomListUseCase"]
