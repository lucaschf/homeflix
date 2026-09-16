"""UploadProfileAvatarUseCase."""

from src.modules.identity.application.dtos.identity_dtos import (
    ProfileOutput,
    UploadProfileAvatarInput,
)
from src.modules.identity.application.errors import (
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.modules.identity.application.ports import AvatarStoragePort
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases._to_output import profile_to_output
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


class UploadProfileAvatarUseCase:
    """Persist a new avatar for a profile and update its ``avatar_url``.

    Enforces ownership before writing — only the caller can change
    their own profile's avatar. Cross-user uploads raise
    :class:`ProfileOwnershipViolation` (HTTP 403). The actual byte
    validation (image decode, MIME allow-list, size cap) lives on
    the ``AvatarStoragePort`` adapter; size/MIME violations bubble
    as :class:`InvalidAvatarImageError` / :class:`AvatarTooLargeError`,
    whose codes the registry maps to HTTP 415 / 413 (ADR-012). Nothing
    on this path names a status.

    The maturity limit is never written here: ``save`` leaves an existing
    profile's limit as stored, so an upload decided on a profile read
    before a concurrent limit change cannot undo it (ADR-035). Nor does
    ``save`` restore a profile deleted after that read: the upload answers
    :class:`ProfileNotFoundException` (HTTP 404) instead.
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        avatar_storage: AvatarStoragePort,
    ) -> None:
        self._uow_factory = uow_factory
        self._avatar_storage = avatar_storage

    async def execute(self, input_dto: UploadProfileAvatarInput) -> ProfileOutput:
        """Validate caller, persist bytes, update ``avatar_url``."""
        caller_id = UserId(input_dto.user_id)
        target_id = ProfileId(input_dto.profile_id)

        # Ownership check first — saves a Pillow decode round-trip
        # for unauthorised callers.
        async with self._uow_factory() as uow:
            existing = await uow.profiles.find_by_id(target_id)
            if existing is None:
                raise ProfileNotFoundException.for_resource(
                    resource_type="Profile",
                    resource_id=input_dto.profile_id,
                )
            if existing.user_id != caller_id:
                raise ProfileOwnershipViolation(
                    message="You do not own this profile",
                )

        # Bytes work happens outside the UoW so a slow Pillow
        # decode doesn't pin a session. Validation errors raise
        # before we re-open the UoW for the persist.
        avatar_url = await self._avatar_storage.save(
            input_dto.profile_id,
            content=input_dto.content,
            declared_mime_type=input_dto.declared_mime_type,
        )

        async with self._uow_factory() as uow:
            # Re-load to avoid races with a concurrent profile
            # update; the avatar_url we apply is independent of
            # any other field that may have changed in the
            # interim.
            current = await uow.profiles.find_by_id(target_id)
            if current is None:
                raise ProfileNotFoundException.for_resource(
                    resource_type="Profile",
                    resource_id=input_dto.profile_id,
                )
            updated = current.with_avatar(avatar_url)
            saved = await uow.profiles.save(updated)
            if saved is None:
                raise ProfileNotFoundException.for_resource(
                    resource_type="Profile",
                    resource_id=input_dto.profile_id,
                )

        return profile_to_output(saved)


__all__ = ["UploadProfileAvatarUseCase"]
