"""CreateProfileUseCase."""

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    ProfileOutput,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases._to_output import profile_to_output
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.value_objects.user_id import UserId


class CreateProfileUseCase:
    """Create a new profile owned by the caller.

    The repository raises ``ValueError`` if the ``user_id`` is unknown
    — left as a low-level error here because authenticated callers
    can only ever pass their own ``user_id`` (sourced from the
    session), so this is a programmer error rather than a domain
    rule.
    """

    def __init__(self, uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: CreateProfileInput) -> ProfileOutput:
        """Persist a new profile and return its full representation."""
        profile = Profile.create(
            user_id=UserId(input_dto.user_id),
            name=ProfileName(input_dto.name),
            is_kids=input_dto.is_kids,
            avatar_url=input_dto.avatar_url,
        )
        async with self._uow_factory() as uow:
            saved = await uow.profiles.save(profile)
        return profile_to_output(saved)


__all__ = ["CreateProfileUseCase"]
