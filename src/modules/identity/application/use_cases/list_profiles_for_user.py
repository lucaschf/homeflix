"""ListProfilesForUserUseCase."""

from src.modules.identity.application.dtos.identity_dtos import (
    ListProfilesForUserInput,
    ProfileOutput,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases._to_output import profile_to_output
from src.shared_kernel.value_objects.user_id import UserId


class ListProfilesForUserUseCase:
    """List every profile owned by the caller, ordered by name."""

    def __init__(self, uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ListProfilesForUserInput) -> list[ProfileOutput]:
        """Return the caller's profiles as a sequence of output DTOs."""
        user_id = UserId(input_dto.user_id)
        async with self._uow_factory() as uow:
            profiles = await uow.profiles.find_by_user(user_id)
        return [profile_to_output(p) for p in profiles]


__all__ = ["ListProfilesForUserUseCase"]
