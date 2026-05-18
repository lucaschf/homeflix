"""GetUserDetailUseCase — admin view of a single user."""

from src.modules.identity.application.dtos.identity_dtos import (
    GetUserDetailInput,
    UserDetail,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases._to_output import profile_to_output
from src.modules.identity.domain.errors import UserNotFoundException
from src.shared_kernel.value_objects.user_id import UserId


class GetUserDetailUseCase:
    """Hydrate a user + their profile list for the admin detail page.

    Profiles are read-only in P3 (per the admin panel design): the
    operator can see grants but profile mutation still goes through
    the user-facing endpoints. Returning them here keeps the page
    to one round-trip.
    """

    def __init__(self, uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: GetUserDetailInput) -> UserDetail:
        """Return the full user detail or raise ``UserNotFoundException``."""
        user_id = UserId(input_dto.user_id)

        async with self._uow_factory() as uow:
            user = await uow.users.find_by_id(user_id)
            if user is None or user.id is None:
                raise UserNotFoundException.for_resource("User", input_dto.user_id)

            profiles = await uow.profiles.find_by_user(user.id)

        return UserDetail(
            id=str(user.id),
            email=user.email.value,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at.isoformat() if user.created_at else "",
            updated_at=user.updated_at.isoformat() if user.updated_at else "",
            profiles=[profile_to_output(p) for p in profiles],
        )


__all__ = ["GetUserDetailUseCase"]
