"""Unit tests for DeleteProfileAvatarUseCase."""

import pytest

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    DeleteProfileAvatarInput,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.delete_profile_avatar import (
    DeleteProfileAvatarUseCase,
)
from src.modules.identity.domain.errors import (
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeAvatarStorage, FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory


class TestDeleteProfileAvatarUseCase:
    async def test_should_clear_avatar_url_and_delete_file(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
    ) -> None:
        owner_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        # Seed the profile with a non-null avatar so the test
        # observes a real "before / after" transition.
        seeded = await creator.execute(
            CreateProfileInput(
                user_id=owner_id.value,
                name="Lucas",
                avatar_url="/api/v1/profiles/x/avatar?v=42",
            )
        )

        use_case = DeleteProfileAvatarUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )
        result = await use_case.execute(
            DeleteProfileAvatarInput(user_id=owner_id.value, profile_id=seeded.id)
        )

        assert result.avatar_url is None
        # Storage delete fired with the right id
        assert fake_avatar_storage.deleted == [seeded.id]
        # Persisted state matches the response
        stored = await fake_uow.profiles.find_by_id(ProfileId(seeded.id))
        assert stored is not None
        assert stored.avatar_url is None

    async def test_should_be_idempotent_when_profile_has_no_avatar(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
    ) -> None:
        # Calling delete on a profile that already has a null
        # avatar_url succeeds — the response just shows it's still
        # null. Storage still gets the (idempotent) delete call.
        owner_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        target = await creator.execute(CreateProfileInput(user_id=owner_id.value, name="Lucas"))

        use_case = DeleteProfileAvatarUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )
        result = await use_case.execute(
            DeleteProfileAvatarInput(user_id=owner_id.value, profile_id=target.id)
        )

        assert result.avatar_url is None
        assert fake_avatar_storage.deleted == [target.id]

    async def test_should_raise_when_profile_does_not_exist(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
    ) -> None:
        use_case = DeleteProfileAvatarUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )

        with pytest.raises(ProfileNotFoundException):
            await use_case.execute(
                DeleteProfileAvatarInput(
                    user_id=UserId.generate().value,
                    profile_id=ProfileId.generate().value,
                )
            )
        assert fake_avatar_storage.deleted == []

    async def test_should_reject_cross_user_delete(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
    ) -> None:
        owner_id = UserId.generate()
        intruder_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        target = await creator.execute(CreateProfileInput(user_id=owner_id.value, name="Lucas"))

        use_case = DeleteProfileAvatarUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )
        with pytest.raises(ProfileOwnershipViolation):
            await use_case.execute(
                DeleteProfileAvatarInput(user_id=intruder_id.value, profile_id=target.id)
            )
        assert fake_avatar_storage.deleted == []
