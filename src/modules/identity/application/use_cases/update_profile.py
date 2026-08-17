"""UpdateProfileUseCase."""

from src.modules.identity.application.dtos.identity_dtos import (
    ProfileOutput,
    UpdateProfileInput,
)
from src.modules.identity.application.errors import (
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases._to_output import profile_to_output
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


class UpdateProfileUseCase:
    """Apply a partial update to an existing profile owned by the caller.

    Enforces ownership: the target profile's ``user_id`` must match
    the caller. Cross-user mutation raises
    :class:`ProfileOwnershipViolation` (HTTP 403). A missing target
    raises :class:`ProfileNotFoundException` (HTTP 404).
    """

    def __init__(self, uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: UpdateProfileInput) -> ProfileOutput:
        """Apply the supplied subset of fields to the target profile and return it."""
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

            updated = existing
            if input_dto.name is not None:
                updated = updated.with_name(ProfileName(input_dto.name))
            if input_dto.is_kids is not None:
                updated = updated.with_kids_flag(is_kids=input_dto.is_kids)
            if input_dto.avatar_url is not None:
                updated = updated.with_avatar(input_dto.avatar_url)
            if input_dto.allowed_library_ids is not None:
                updated = updated.with_allowed_library_ids(input_dto.allowed_library_ids)

            saved = await uow.profiles.save(updated)

        return profile_to_output(saved)


__all__ = ["UpdateProfileUseCase"]
