"""DeleteProfileUseCase."""

from src.modules.identity.application.dtos.identity_dtos import DeleteProfileInput
from src.modules.identity.application.errors import (
    CannotDeleteLastProfileError,
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.modules.identity.application.ports import AvatarStoragePort
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


class DeleteProfileUseCase:
    """Soft-delete a profile owned by the caller.

    Enforces two invariants:

    - **Ownership**: the target profile must belong to the caller.
      Cross-user deletion raises :class:`ProfileOwnershipViolation`
      (HTTP 403).
    - **Last-profile guard**: a user must always have at least one
      profile so that ``get_current_profile`` always has something
      to resolve. Deleting the last remaining profile raises
      :class:`CannotDeleteLastProfileError` (HTTP 409).

    Cascade-deletes the profile's uploaded avatar file via the
    storage port. The port's ``delete`` is idempotent so the call
    is safe whether the profile ever had an avatar or not.
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        avatar_storage: AvatarStoragePort,
    ) -> None:
        self._uow_factory = uow_factory
        self._avatar_storage = avatar_storage

    async def execute(self, input_dto: DeleteProfileInput) -> None:
        """Soft-delete the target profile after enforcing ownership and last-profile guards."""
        caller_id = UserId(input_dto.user_id)
        target_id = ProfileId(input_dto.profile_id)

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

            count = await uow.profiles.count_for_user(caller_id)
            if count <= 1:
                raise CannotDeleteLastProfileError(
                    message="Cannot delete your only profile",
                )

            await uow.profiles.delete(target_id)

        # Cascade-delete the avatar file after the soft-delete row
        # update commits. A filesystem hiccup at this point leaves
        # an orphan file (logged by the storage adapter) but never
        # blocks the row delete itself.
        await self._avatar_storage.delete(input_dto.profile_id)


__all__ = ["DeleteProfileUseCase"]
