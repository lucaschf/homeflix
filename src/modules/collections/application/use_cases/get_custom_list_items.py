"""GetCustomListItemsUseCase - List items in a custom list with metadata."""

import logging

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import (
    CustomListItemsOutput,
    GetCustomListItemsInput,
)
from src.modules.collections.application.ports import (
    MediaLookupPort,
    ProfileLibraryAccessPort,
    ProgressLookupPort,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.application.use_cases._item_projection import project_items
from src.shared_kernel.value_objects.profile_id import ProfileId

_logger = logging.getLogger(__name__)


class GetCustomListItemsUseCase:
    """List items in a custom list, for either the owner or a follower.

    Owner path: the caller owns the list and sees every item they own
    — no access filter, ``hidden_count`` is ``0``.

    Follower path: the caller doesn't own the list but follows it (and
    it is still shared). The read resolves the *owner's* current items
    (the view is live) and filters each through the *follower's* library
    access, so a followed list can never leak titles the follower's
    profile can't see (ADR-010). Hidden items are counted, not shown.

    A caller who neither owns nor follows the list gets a 404 — same as
    a follower of a list that was deleted or unshared (no dangling read).
    """

    def __init__(
        self,
        uow_factory: CollectionsUnitOfWorkFactory,
        media_lookup: MediaLookupPort,
        progress_lookup: ProgressLookupPort,
        profile_library_access: ProfileLibraryAccessPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
            media_lookup: Port for resolving media display metadata.
            progress_lookup: Port for resolving the caller's watch progress.
            profile_library_access: Port for the follower's library ACL.
        """
        self._uow_factory = uow_factory
        self._media_lookup = media_lookup
        self._progress_lookup = progress_lookup
        self._profile_library_access = profile_library_access

    async def execute(self, input_dto: GetCustomListItemsInput) -> CustomListItemsOutput:
        """Execute the use case.

        Args:
            input_dto: Contains ``profile_id``, ``list_id`` and language.

        Returns:
            ``CustomListItemsOutput`` with the visible items and the
            count hidden by the follower's access (``0`` for owners).

        Raises:
            ResourceNotFoundException: If the caller neither owns nor
                follows the list, or the followed list is gone/unshared.
        """
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            owned = await uow.custom_lists.find_by_id(input_dto.list_id, profile_id)
            if owned is not None:
                items = await uow.custom_lists.list_items(input_dto.list_id, profile_id)
                allowed = None  # owner sees everything they own
            else:
                owner_list = await uow.custom_lists.find_by_id_unscoped(input_dto.list_id)
                if owner_list is None or owner_list.id is None or not owner_list.is_shared:
                    raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)
                follow = await uow.list_follows.find(profile_id, owner_list.id)
                if follow is None:
                    raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)
                items = await uow.custom_lists.list_items(input_dto.list_id, owner_list.profile_id)
                allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)

        outputs, hidden_count = await project_items(
            items,
            media_lookup=self._media_lookup,
            progress_lookup=self._progress_lookup,
            lang=input_dto.lang,
            profile_id=input_dto.profile_id,
            allowed_library_ids=allowed,
        )
        _logger.info(
            "Custom list %s: %d visible item(s), %d hidden by access",
            input_dto.list_id,
            len(outputs),
            hidden_count,
        )
        return CustomListItemsOutput(items=tuple(outputs), hidden_count=hidden_count)


__all__ = ["GetCustomListItemsUseCase"]
