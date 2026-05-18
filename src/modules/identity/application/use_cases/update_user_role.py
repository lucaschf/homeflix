"""UpdateUserRoleUseCase — flip a user between ADMIN and MEMBER."""

from src.modules.identity.application.dtos.identity_dtos import (
    UpdateUserRoleInput,
    UserSummary,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.errors import (
    CannotDemoteLastAdminError,
    UserNotFoundException,
)
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.shared_kernel.value_objects.user_id import UserId


class UpdateUserRoleUseCase:
    """Flip a user's role.

    Two guards:

    * Demoting the last active admin is refused with
      ``CannotDemoteLastAdminError`` — including the case where the
      acting admin is demoting themselves while no other admin
      exists.
    * Re-applying the same role is a no-op (the use case still
      returns the latest summary so the UI re-renders cleanly).
    """

    def __init__(self, uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: UpdateUserRoleInput) -> UserSummary:
        """Apply the requested role and return the refreshed summary."""
        user_id = UserId(input_dto.user_id)
        new_role = UserRole(input_dto.role)

        async with self._uow_factory() as uow:
            user = await uow.users.find_by_id(user_id)
            if user is None or user.id is None:
                raise UserNotFoundException.for_resource("User", input_dto.user_id)

            if user.role != new_role and user.role == UserRole.ADMIN:
                admin_count = await uow.users.count_active_admins()
                if admin_count <= 1:
                    raise CannotDemoteLastAdminError(
                        message=(
                            "Cannot demote the last active admin — " "promote another user first."
                        ),
                    )

            if user.role != new_role:
                updated = user.with_role(new_role)
                saved = await uow.users.save(updated)
            else:
                saved = user

            profile_count = await uow.profiles.count_for_user(saved.id)

        return UserSummary(
            id=str(saved.id),
            email=saved.email.value,
            role=saved.role.value,
            is_active=saved.is_active,
            profile_count=profile_count,
            created_at=saved.created_at.isoformat() if saved.created_at else "",
        )


__all__ = ["UpdateUserRoleUseCase"]
