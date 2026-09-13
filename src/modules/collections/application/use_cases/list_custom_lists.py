"""ListCustomListsUseCase - List owned + followed custom lists for a profile."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from src.modules.collections.application.dtos import CustomListOutput
from src.modules.collections.application.use_cases._title_gate import (
    title_of,
    titles_withheld_by_maturity,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from src.modules.collections.application.ports import (
        MediaLookupPort,
        ProfileLookupPort,
        ProfileViewingPolicyPort,
    )
    from src.modules.collections.application.unit_of_work import (
        CollectionsUnitOfWorkFactory,
    )
    from src.modules.collections.domain.entities import CustomList, CustomListItem


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

    ``item_count`` is the stored count. For a caller under a maturity
    limit it leaves out the titles that limit withholds — on owned and
    followed rows alike, by the caller's own policy — so it matches what
    the list's items read and the shared preview show (ADR-035).
    """

    def __init__(
        self,
        uow_factory: CollectionsUnitOfWorkFactory,
        profile_lookup: ProfileLookupPort,
        media_lookup: MediaLookupPort,
        profile_viewing_policy: ProfileViewingPolicyPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
            profile_lookup: Port resolving the owners' display names.
            media_lookup: Port for asking the catalog which titles are visible.
            profile_viewing_policy: Port resolving the caller's viewing policy.
        """
        self._uow_factory = uow_factory
        self._profile_lookup = profile_lookup
        self._media_lookup = media_lookup
        self._profile_viewing_policy = profile_viewing_policy

    async def execute(self, input_dto: ListCustomListsInput) -> list[CustomListOutput]:
        """Return owned lists followed by the caller's followed lists.

        The items are read only under a maturity limit, inside the list
        transaction; the catalog is asked after it closes, once for every
        list together.
        """
        profile_id = ProfileId(input_dto.profile_id)
        policy = await self._profile_viewing_policy.find_for_profile(profile_id)
        items_by_list: dict[str, list[CustomListItem]] = {}
        async with self._uow_factory() as uow:
            owned = await uow.custom_lists.list_all(profile_id)
            follows = await uow.list_follows.list_for_follower(profile_id)

            followed_lists: list[CustomList] = []
            for follow in follows:
                owner_list = await uow.custom_lists.find_by_id_unscoped(follow.list_id.value)
                # Drop follows whose target is gone or no longer shared.
                if owner_list is not None and owner_list.is_shared:
                    followed_lists.append(owner_list)

            if policy.restricts_maturity:
                for custom_list in [*owned, *followed_lists]:
                    list_id = str(custom_list.id)
                    items_by_list[list_id] = await uow.custom_lists.list_items(
                        list_id, custom_list.profile_id
                    )

        owner_names = await self._profile_lookup.get_names(
            [cl.profile_id.value for cl in followed_lists]
        )
        withheld = await titles_withheld_by_maturity(
            self._media_lookup,
            [title_of(item.media_id) for items in items_by_list.values() for item in items],
            policy,
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
        if not withheld:
            return results
        return [
            replace(
                output,
                item_count=output.item_count
                - sum(1 for item in items_by_list[output.id] if item.media_id.value in withheld),
            )
            for output in results
        ]


__all__ = ["ListCustomListsInput", "ListCustomListsUseCase"]
