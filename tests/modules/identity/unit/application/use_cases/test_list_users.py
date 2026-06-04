"""Unit tests for ListUsersUseCase."""

import pytest

from src.modules.identity.application.dtos.identity_dtos import CreateProfileInput, ListUsersInput
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.list_users import ListUsersUseCase
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory

pytestmark = pytest.mark.unit


async def _seed_user(
    fake_uow: FakeIdentityUnitOfWork,
    *,
    email: str,
    role: UserRole = UserRole.MEMBER,
) -> User:
    async with fake_uow:
        return await fake_uow.users.save(
            User.create(email=Email(email), role=role),
        )


class TestListUsersUseCase:
    async def test_should_return_every_non_deleted_user_when_no_filter(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        await _seed_user(fake_uow, email="alice@example.com")
        await _seed_user(fake_uow, email="bob@example.com", role=UserRole.ADMIN)

        use_case = ListUsersUseCase(uow_factory=fake_uow_factory)
        rows = await use_case.execute(ListUsersInput())

        emails = sorted(r.email for r in rows)
        assert emails == ["alice@example.com", "bob@example.com"]

    async def test_should_filter_by_role(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        await _seed_user(fake_uow, email="alice@example.com")
        await _seed_user(fake_uow, email="root@example.com", role=UserRole.ADMIN)

        rows = await ListUsersUseCase(uow_factory=fake_uow_factory).execute(
            ListUsersInput(role=UserRole.ADMIN),
        )

        assert [r.email for r in rows] == ["root@example.com"]

    async def test_should_include_profile_count_per_row(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        user = await _seed_user(fake_uow, email="alice@example.com")
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        await creator.execute(CreateProfileInput(user_id=str(user.id), name="Adult"))
        await creator.execute(CreateProfileInput(user_id=str(user.id), name="Kids"))

        rows = await ListUsersUseCase(uow_factory=fake_uow_factory).execute(
            ListUsersInput(),
        )

        [row] = rows
        assert row.profile_count == 2
