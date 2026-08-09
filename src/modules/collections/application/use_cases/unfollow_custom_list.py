"""UnfollowCustomListUseCase - Stop following a shared list."""

from src.modules.collections.application.dtos import UnfollowCustomListInput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.value_objects import ListId
from src.shared_kernel.value_objects.profile_id import ProfileId


class UnfollowCustomListUseCase:
    """Remove the caller's follow of a list.

    Idempotent: unfollowing a list the caller doesn't follow is a
    no-op success, so the endpoint always returns 204. A malformed
    ``list_id`` also resolves to a no-op rather than an error — there
    is nothing to remove either way.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: UnfollowCustomListInput) -> None:
        """Soft-delete the caller's follow of ``list_id`` if it exists."""
        try:
            list_id = ListId(input_dto.list_id)
        except Exception:  # — malformed id → nothing to unfollow
            return

        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            await uow.list_follows.remove(profile_id, list_id)


__all__ = ["UnfollowCustomListUseCase"]
