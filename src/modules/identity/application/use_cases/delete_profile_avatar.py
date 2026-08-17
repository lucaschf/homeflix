"""DeleteProfileAvatarUseCase."""

from src.modules.identity.application.dtos.identity_dtos import (
    DeleteProfileAvatarInput,
    ProfileOutput,
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


class DeleteProfileAvatarUseCase:
    """Clear a profile's avatar (sets ``avatar_url`` to ``None`` + deletes file).

    Enforces ownership: the target profile's ``user_id`` must match
    the caller. The storage call is idempotent so a second delete on
    an already-cleared profile succeeds without error — the response
    just returns the (still-empty) profile.
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        avatar_storage: AvatarStoragePort,
    ) -> None:
        self._uow_factory = uow_factory
        self._avatar_storage = avatar_storage

    async def execute(self, input_dto: DeleteProfileAvatarInput) -> ProfileOutput:
        """Authorise → clear ``avatar_url`` → remove the file."""
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
            updated = existing.with_avatar(None)
            saved = await uow.profiles.save(updated)

        # Storage delete after the row update so a partial failure
        # leaves the profile pointing at a valid (or absent) file
        # rather than referencing one we just removed.
        await self._avatar_storage.delete(input_dto.profile_id)

        return profile_to_output(saved)


__all__ = ["DeleteProfileAvatarUseCase"]
