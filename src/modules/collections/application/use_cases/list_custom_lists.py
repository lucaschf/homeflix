"""ListCustomListsUseCase - List owned + followed custom lists for a profile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.modules.collections.application.dtos import CustomListOutput
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from src.modules.collections.application.ports import ProfileLookupPort
    from src.modules.collections.application.unit_of_work import (
        CollectionsUnitOfWorkFactory,
    )
    from src.modules.collections.domain.entities import CustomList


@dataclass(frozen=True)
class ListCustomListsInput:
    """Input for ListCustomListsUseCase."""

    profile_id: str


class ListCustomListsUseCase:
    """List the caller's own lists plus the lists they follow.

    One "My Lists" surface: owned rows first (most recently updated),
    then followed rows flagged ``is_followed`` with the owner's display
    name. Followed rows are read-only and don't count against the
    owner's ``MAX_LISTS`` quota. A followed list whose owner deleted or
    unshared it is silently dropped — no dangling read.
    """

    def __init__(
        self,
        uow_factory: CollectionsUnitOfWorkFactory,
        profile_lookup: ProfileLookupPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._profile_lookup = profile_lookup

    async def execute(self, input_dto: ListCustomListsInput) -> list[CustomListOutput]:
        """Return owned lists followed by the caller's followed lists."""
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            owned = await uow.custom_lists.list_all(profile_id)
            follows = await uow.list_follows.list_for_follower(profile_id)

            followed_lists: list[CustomList] = []
            for follow in follows:
                owner_list = await uow.custom_lists.find_by_id_unscoped(follow.list_id.value)
                # Drop follows whose target is gone or no longer shared.
                if owner_list is not None and owner_list.is_shared:
                    followed_lists.append(owner_list)

        owner_names = await self._profile_lookup.get_names(
            [cl.profile_id.value for cl in followed_lists]
        )

        results = [CustomListOutput.from_entity(cl) for cl in owned]
        results.extend(
            CustomListOutput.from_entity(
                cl,
                is_followed=True,
                owner_name=owner_names.get(cl.profile_id.value),
            )
            for cl in followed_lists
        )
        return results


__all__ = ["ListCustomListsInput", "ListCustomListsUseCase"]
