"""Unit tests for UpdateUserRoleUseCase."""

import pytest

from src.modules.identity.application.dtos.identity_dtos import UpdateUserRoleInput
from src.modules.identity.application.errors import UserNotFoundException
from src.modules.identity.application.use_cases.update_user_role import (
    UpdateUserRoleUseCase,
)
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.errors import CannotDemoteLastAdminError
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory

pytestmark = pytest.mark.unit


async def _seed(fake_uow: FakeIdentityUnitOfWork, *, email: str, role: UserRole) -> User:
    async with fake_uow:
        return await fake_uow.users.save(User.create(email=Email(email), role=role))


class TestUpdateUserRoleUseCase:
    async def test_should_flip_member_to_admin(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        target = await _seed(fake_uow, email="m@example.com", role=UserRole.MEMBER)

        result = await UpdateUserRoleUseCase(uow_factory=fake_uow_factory).execute(
            UpdateUserRoleInput(
                user_id=str(target.id),
                role=UserRole.ADMIN,
                acting_admin_id=str(UserId.generate()),
            ),
        )

        assert result.role == "admin"

    async def test_should_refuse_demoting_last_active_admin(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        only_admin = await _seed(fake_uow, email="root@example.com", role=UserRole.ADMIN)

        with pytest.raises(CannotDemoteLastAdminError):
            await UpdateUserRoleUseCase(uow_factory=fake_uow_factory).execute(
                UpdateUserRoleInput(
                    user_id=str(only_admin.id),
                    role=UserRole.MEMBER,
                    acting_admin_id=str(only_admin.id),
                ),
            )

    async def test_should_allow_demoting_admin_when_another_admin_exists(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        await _seed(fake_uow, email="a1@example.com", role=UserRole.ADMIN)
        a2 = await _seed(fake_uow, email="a2@example.com", role=UserRole.ADMIN)

        result = await UpdateUserRoleUseCase(uow_factory=fake_uow_factory).execute(
            UpdateUserRoleInput(
                user_id=str(a2.id),
                role=UserRole.MEMBER,
                acting_admin_id=str(a2.id),
            ),
        )

        assert result.role == "member"

    async def test_should_raise_when_user_not_found(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        with pytest.raises(UserNotFoundException):
            await UpdateUserRoleUseCase(uow_factory=fake_uow_factory).execute(
                UpdateUserRoleInput(
                    user_id=str(UserId.generate()),
                    role=UserRole.ADMIN,
                    acting_admin_id=str(UserId.generate()),
                ),
            )
