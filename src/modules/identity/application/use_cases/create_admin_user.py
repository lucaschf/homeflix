"""CreateAdminUserUseCase — admin creates a fresh user account."""

from src.modules.identity.application.dtos.identity_dtos import (
    CreateAdminUserInput,
    UserSummary,
)
from src.modules.identity.application.ports import PasswordHasherPort
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.errors import UserEmailAlreadyExistsError
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole


class CreateAdminUserUseCase:
    """Admin creates a user via email + initial password + role.

    The created user is ``is_verified=True`` and ``is_active=True``
    so they can log in immediately; they're expected to change the
    initial password from ``/settings`` after first login. Profile
    bootstrap is *not* part of this use case — the user creates
    their first profile themselves on first sign-in (matches the
    existing flow members already see).

    Raises:
        UserEmailAlreadyExistsError: when ``email`` is already used
            by a live or soft-deleted user (the DB-level unique
            constraint would crash an insert otherwise).
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        password_hasher: PasswordHasherPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher

    async def execute(self, input_dto: CreateAdminUserInput) -> UserSummary:
        """Hash the password, persist a new user, return the summary."""
        email = Email(input_dto.email)
        role = UserRole(input_dto.role)
        hashed = self._password_hasher.hash(input_dto.password)

        async with self._uow_factory() as uow:
            existing = await uow.users.find_by_email(email)
            if existing is not None:
                raise UserEmailAlreadyExistsError(
                    message=f"Email {input_dto.email!r} is already in use",
                )

            user = User.create(
                email=email,
                role=role,
                is_verified=True,
                hashed_password=hashed,
            )
            saved = await uow.users.save(user)

        return UserSummary(
            id=str(saved.id),
            email=saved.email.value,
            role=saved.role.value,
            is_active=saved.is_active,
            profile_count=0,
            created_at=saved.created_at.isoformat() if saved.created_at else "",
        )


__all__ = ["CreateAdminUserUseCase"]
