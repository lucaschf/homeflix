"""Unit tests for DeleteProfileUseCase."""

import pytest

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    DeleteProfileInput,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.delete_profile import (
    DeleteProfileUseCase,
)
from src.modules.identity.domain.errors import (
    CannotDeleteLastProfileError,
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory


class TestDeleteProfileUseCase:
    async def test_should_soft_delete_when_user_has_more_than_one_profile(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage,
    ):
        caller_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        keep = await creator.execute(CreateProfileInput(user_id=caller_id.value, name="Keep"))
        doomed = await creator.execute(CreateProfileInput(user_id=caller_id.value, name="Doomed"))

        use_case = DeleteProfileUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )
        await use_case.execute(
            DeleteProfileInput(
                user_id=caller_id.value,
                profile_id=doomed.id,
            )
        )

        # Deleted profile is gone, the other survives.
        assert await fake_uow.profiles.find_by_id(ProfileId(doomed.id)) is None
        assert await fake_uow.profiles.find_by_id(ProfileId(keep.id)) is not None
        assert await fake_uow.profiles.count_for_user(caller_id) == 1

    async def test_should_raise_when_deleting_last_profile(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory, fake_avatar_storage
    ):
        caller_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        only = await creator.execute(CreateProfileInput(user_id=caller_id.value, name="Only"))

        use_case = DeleteProfileUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )

        with pytest.raises(CannotDeleteLastProfileError):
            await use_case.execute(
                DeleteProfileInput(
                    user_id=caller_id.value,
                    profile_id=only.id,
                )
            )

    async def test_should_raise_when_profile_does_not_exist(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory, fake_avatar_storage
    ):
        use_case = DeleteProfileUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )

        with pytest.raises(ProfileNotFoundException):
            await use_case.execute(
                DeleteProfileInput(
                    user_id=UserId.generate().value,
                    profile_id=ProfileId.generate().value,
                )
            )

    async def test_should_raise_when_caller_is_not_the_owner(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory, fake_avatar_storage
    ):
        owner_id = UserId.generate()
        intruder_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        # Owner has 2 profiles so the last-profile guard wouldn't kick in.
        await creator.execute(CreateProfileInput(user_id=owner_id.value, name="Other"))
        target = await creator.execute(CreateProfileInput(user_id=owner_id.value, name="Target"))

        use_case = DeleteProfileUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )

        with pytest.raises(ProfileOwnershipViolation):
            await use_case.execute(
                DeleteProfileInput(
                    user_id=intruder_id.value,
                    profile_id=target.id,
                )
            )
