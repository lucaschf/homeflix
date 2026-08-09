"""GetSharedListPreviewUseCase - Read-only preview of a shared list by token."""

from pydantic import ValidationError

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import DomainValidationException
from src.modules.collections.application.dtos import (
    GetSharedListPreviewInput,
    SharedListMetaOutput,
    SharedListPreviewOutput,
)
from src.modules.collections.application.ports import (
    MediaLookupPort,
    ProfileLibraryAccessPort,
    ProfileLookupPort,
    ProgressLookupPort,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.application.use_cases._item_projection import project_items
from src.modules.collections.domain.value_objects import ShareToken
from src.shared_kernel.value_objects.profile_id import ProfileId


class GetSharedListPreviewUseCase:
    """Resolve a shared list by token for a read-only, access-filtered preview.

    The preview is what a member sees on the ``/lists/shared/:token``
    landing page before deciding to follow. It returns the owner's
    current list meta and items, but every item is filtered through the
    *caller's* library access (ADR-010) — a kids or restricted profile
    never sees titles it isn't allowed to, and ``hidden_count`` reports
    how many were withheld. A fully-restricted list previews as
    empty-with-notice, not an error.

    An unknown or revoked token yields a 404. Auth is enforced at the
    route (a HomeFlix member), so there is no public/anonymous access.
    """

    def __init__(
        self,
        uow_factory: CollectionsUnitOfWorkFactory,
        media_lookup: MediaLookupPort,
        progress_lookup: ProgressLookupPort,
        profile_library_access: ProfileLibraryAccessPort,
        profile_lookup: ProfileLookupPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._media_lookup = media_lookup
        self._progress_lookup = progress_lookup
        self._profile_library_access = profile_library_access
        self._profile_lookup = profile_lookup

    async def execute(self, input_dto: GetSharedListPreviewInput) -> SharedListPreviewOutput:
        """Return the access-filtered preview for the token.

        Raises:
            ResourceNotFoundException: If the token is unknown, revoked,
                or malformed.
        """
        profile_id = ProfileId(input_dto.profile_id)
        token = self._parse_token(input_dto.token)

        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_share_token(token)
            if custom_list is None or custom_list.id is None:
                raise ResourceNotFoundException.for_resource("SharedList", input_dto.token)

            items = await uow.custom_lists.list_items(custom_list.id.value, custom_list.profile_id)
            follow = await uow.list_follows.find(profile_id, custom_list.id)

        owner_names = await self._profile_lookup.get_names([custom_list.profile_id.value])
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)

        outputs, hidden_count = await project_items(
            items,
            media_lookup=self._media_lookup,
            progress_lookup=self._progress_lookup,
            lang=input_dto.lang,
            profile_id=input_dto.profile_id,
            allowed_library_ids=allowed,
        )

        return SharedListPreviewOutput(
            list=SharedListMetaOutput(
                id=custom_list.id.value,
                name=custom_list.name.value,
                description=custom_list.description,
                owner_name=owner_names.get(custom_list.profile_id.value),
                item_count=custom_list.item_count,
            ),
            items=tuple(outputs),
            hidden_count=hidden_count,
            is_following=follow is not None,
        )

    @staticmethod
    def _parse_token(raw: str) -> ShareToken:
        """Parse the token, mapping a malformed value to a 404.

        A too-short or malformed token can't identify any real list, so
        it is surfaced as "not found" rather than a validation error.
        """
        try:
            return ShareToken(raw)
        except (DomainValidationException, ValidationError) as exc:
            raise ResourceNotFoundException.for_resource("SharedList", raw) from exc


__all__ = ["GetSharedListPreviewUseCase"]
