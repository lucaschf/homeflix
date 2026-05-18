"""Unit tests for GetUserDetailUseCase."""

import pytest

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    GetUserDetailInput,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.get_user_detail import (
    GetUserDetailUseCase,
)
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.errors import UserNotFoundException
from src.modules.identity.domain.value_objects.email import Email
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory

pytestmark = pytest.mark.unit


class TestGetUserDetailUseCase:
    async def test_should_return_user_with_profiles(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        async with fake_uow:
            user = await fake_uow.users.save(User.create(email=Email("m@example.com")))
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        await creator.execute(CreateProfileInput(user_id=str(user.id), name="Adult"))

        detail = await GetUserDetailUseCase(uow_factory=fake_uow_factory).execute(
            GetUserDetailInput(user_id=str(user.id)),
        )

        assert detail.email == "m@example.com"
        assert len(detail.profiles) == 1
        assert detail.profiles[0].name == "Adult"

    async def test_should_raise_when_user_not_found(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        with pytest.raises(UserNotFoundException):
            await GetUserDetailUseCase(uow_factory=fake_uow_factory).execute(
                GetUserDetailInput(user_id=str(UserId.generate())),
            )
