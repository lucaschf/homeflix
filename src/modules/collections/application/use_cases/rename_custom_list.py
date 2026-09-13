"""RenameCustomListUseCase - Rename an existing custom list."""

from dataclasses import replace
from typing import TYPE_CHECKING

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CustomListOutput,
    RenameCustomListInput,
)
from src.modules.collections.application.ports import (
    MediaLookupPort,
    ProfileViewingPolicyPort,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.application.use_cases._title_gate import (
    title_of,
    titles_withheld_by_maturity,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from src.modules.collections.domain.entities import CustomListItem


class RenameCustomListUseCase:
    """Rename an existing custom list owned by the caller's profile.

    The returned ``item_count`` is the stored count, except for a caller
    under a maturity limit: then it leaves out the titles that limit
    withholds, as the lists read does (ADR-035).
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

    async def execute(self, input_dto: RenameCustomListInput) -> CustomListOutput:
        """Rename the list, enforcing per-profile uniqueness.

        The policy is read before the list transaction opens and the
        catalog after it closes, so no collections transaction is held
        while Identity and Media answer.
        """
        profile_id = ProfileId(input_dto.profile_id)
        policy = await self._profile_viewing_policy.find_for_profile(profile_id)
        items: list[CustomListItem] = []
        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id, profile_id)
            if not custom_list:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            new_name = input_dto.name.strip()
            existing = await uow.custom_lists.find_by_name(new_name, profile_id)
            if existing and str(existing.id) != input_dto.list_id:
                raise BusinessRuleViolationException(
                    message=f"A list named '{new_name}' already exists",
                    message_code="CUSTOM_LIST_NAME_DUPLICATE",
                    rule_code="CUSTOM_LIST_NAME_DUPLICATE",
                )

            updated = custom_list.with_details(
                name=new_name,
                description=(input_dto.description or "").strip() or None,
            )
            saved = await uow.custom_lists.update(updated)
            if policy.restricts_maturity:
                items = await uow.custom_lists.list_items(input_dto.list_id, profile_id)

        output = CustomListOutput.from_entity(saved)
        withheld = await titles_withheld_by_maturity(
            self._media_lookup, [title_of(item.media_id) for item in items], policy
        )
        if not withheld:
            return output
        hidden = sum(1 for item in items if item.media_id.value in withheld)
        return replace(output, item_count=output.item_count - hidden)


__all__ = ["RenameCustomListUseCase"]
