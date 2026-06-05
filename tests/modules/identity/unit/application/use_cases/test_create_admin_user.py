"""Unit tests for CreateAdminUserUseCase."""

import pytest

from src.modules.identity.application.dtos.identity_dtos import CreateAdminUserInput
from src.modules.identity.application.ports import PasswordHasherPort
from src.modules.identity.application.use_cases.create_admin_user import (
    CreateAdminUserUseCase,
)
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.errors import UserEmailAlreadyExistsError
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory

pytestmark = pytest.mark.unit


class _FakeHasher(PasswordHasherPort):
    def hash(self, password: str) -> str:
        return f"hashed::{password}"


class TestCreateAdminUserUseCase:
    async def test_should_persist_user_with_hashed_password(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        use_case = CreateAdminUserUseCase(
            uow_factory=fake_uow_factory,
            password_hasher=_FakeHasher(),
        )

        summary = await use_case.execute(
            CreateAdminUserInput(
                email="new@example.com",
                password="hunter22ish",
                role=UserRole.MEMBER,
            ),
        )

        assert summary.email == "new@example.com"
        assert summary.role == "member"
        async with fake_uow:
            stored = await fake_uow.users.find_by_email(Email("new@example.com"))
        assert stored is not None
        assert stored.hashed_password == "hashed::hunter22ish"
        assert stored.is_verified is True

    async def test_should_default_role_to_member(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        use_case = CreateAdminUserUseCase(
            uow_factory=fake_uow_factory,
            password_hasher=_FakeHasher(),
        )

        summary = await use_case.execute(
            CreateAdminUserInput(email="m@example.com", password="abcdefgh"),
        )

        assert summary.role == "member"

    async def test_should_raise_when_email_already_exists(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        async with fake_uow:
            await fake_uow.users.save(User.create(email=Email("dup@example.com")))

        use_case = CreateAdminUserUseCase(
            uow_factory=fake_uow_factory,
            password_hasher=_FakeHasher(),
        )

        with pytest.raises(UserEmailAlreadyExistsError):
            await use_case.execute(
                CreateAdminUserInput(email="dup@example.com", password="abcdefgh"),
            )
