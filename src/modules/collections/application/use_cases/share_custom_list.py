"""ShareCustomListUseCase - Mint (or return) a share token for a list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import (
    ShareCustomListInput,
    ShareCustomListOutput,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.shared_kernel.value_objects.profile_id import ProfileId

# Client-side landing path for a shared list. The frontend routes
# ``/lists/shared/:token`` to the read-only preview (mirrors the
# ``SHARE_ENABLED`` contract). Kept here so the API returns a
# ready-to-copy relative path, not just the bare token.
_SHARE_URL_TEMPLATE = "/lists/shared/{token}"


class ShareCustomListUseCase:
    """Share a list the caller owns, returning a stable link.

    Idempotent: sharing an already-shared list returns the existing
    token (the link a member already copied keeps working). Ownership
    is enforced by the profile-scoped repository lookup — a caller who
    doesn't own the list gets a 404, never another profile's token.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ShareCustomListInput) -> ShareCustomListOutput:
        """Mint or return the list's share token.

        Raises:
            ResourceNotFoundException: If the list doesn't exist or the
                caller doesn't own it.
        """
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id, profile_id)
            if custom_list is None:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            shared = custom_list.shared()
            if shared is not custom_list:
                shared = await uow.custom_lists.update(shared)

        # ``shared()`` always yields a token; guard defensively so a
        # regression surfaces as a clear 500 rather than an AttributeError.
        token = shared.share_token
        if token is None:  # pragma: no cover - invariant of shared()
            raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)
        return ShareCustomListOutput(
            token=token.value,
            url_path=_SHARE_URL_TEMPLATE.format(token=token.value),
        )


__all__ = ["ShareCustomListUseCase"]
