"""RevokeCustomListShareUseCase - Stop sharing a list."""

import logging

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import RevokeCustomListShareInput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.shared_kernel.value_objects.profile_id import ProfileId

_logger = logging.getLogger(__name__)


class RevokeCustomListShareUseCase:
    """Revoke a list's share, invalidating the token and dropping followers.

    "Revoke" means *stop sharing*: the token is cleared (so the old
    link 404s) **and** every existing follow is removed, so followers
    see the list disappear from their surface with no dangling read.
    Both writes share one Unit of Work so a partial failure rolls back.

    Idempotent: revoking a list that isn't shared is a no-op success.
    Ownership is enforced by the profile-scoped lookup.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: RevokeCustomListShareInput) -> None:
        """Clear the token and drop all follows of the list.

        Raises:
            ResourceNotFoundException: If the list doesn't exist or the
                caller doesn't own it.
        """
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id, profile_id)
            if custom_list is None or custom_list.id is None:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            unshared = custom_list.unshared()
            if unshared is not custom_list:
                await uow.custom_lists.update(unshared)
            removed = await uow.list_follows.remove_all_for_list(custom_list.id)

        if removed:
            _logger.info(
                "Revoked share of list %s and dropped %d follower(s)",
                input_dto.list_id,
                removed,
            )


__all__ = ["RevokeCustomListShareUseCase"]
