"""Unit tests for UpdateProfileUseCase."""

import pytest

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    UpdateProfileInput,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.update_profile import (
    UpdateProfileUseCase,
)
from src.modules.identity.domain.errors import (
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWorkFactory


class TestUpdateProfileUseCase:
    async def test_should_update_only_supplied_fields(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ):
        caller_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        original = await creator.execute(
            CreateProfileInput(
                user_id=caller_id.value,
                name="Lucas",
                is_kids=False,
                avatar_url="https://x/old.png",
            )
        )

        use_case = UpdateProfileUseCase(uow_factory=fake_uow_factory)
        output = await use_case.execute(
            UpdateProfileInput(
                user_id=caller_id.value,
                profile_id=original.id,
                name="Luc",  # only name supplied
            )
        )

        assert output.id == original.id
        assert output.name == "Luc"  # changed
        assert output.avatar_url == "https://x/old.png"  # unchanged
        assert output.is_kids is False  # unchanged

    async def test_should_update_kids_flag_only(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ):
        caller_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        original = await creator.execute(CreateProfileInput(user_id=caller_id.value, name="Kids"))

        use_case = UpdateProfileUseCase(uow_factory=fake_uow_factory)
        output = await use_case.execute(
            UpdateProfileInput(
                user_id=caller_id.value,
                profile_id=original.id,
                is_kids=True,
            )
        )

        assert output.is_kids is True
        assert output.name == "Kids"  # unchanged

    async def test_should_raise_when_profile_does_not_exist(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ):
        use_case = UpdateProfileUseCase(uow_factory=fake_uow_factory)

        with pytest.raises(ProfileNotFoundException):
            await use_case.execute(
                UpdateProfileInput(
                    user_id=UserId.generate().value,
                    profile_id=ProfileId.generate().value,
                    name="Whatever",
                )
            )

    async def test_should_raise_when_caller_is_not_the_owner(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ):
        owner_id = UserId.generate()
        intruder_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        target = await creator.execute(
            CreateProfileInput(user_id=owner_id.value, name="OwnersProfile")
        )

        use_case = UpdateProfileUseCase(uow_factory=fake_uow_factory)

        with pytest.raises(ProfileOwnershipViolation):
            await use_case.execute(
                UpdateProfileInput(
                    user_id=intruder_id.value,
                    profile_id=target.id,
                    name="Hijacked",
                )
            )
