"""Unit tests for UploadProfileAvatarUseCase."""

import pytest

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    UploadProfileAvatarInput,
)
from src.modules.identity.application.errors import (
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.upload_profile_avatar import (
    UploadProfileAvatarUseCase,
)
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeAvatarStorage, FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory


class TestUploadProfileAvatarUseCase:
    async def test_should_persist_bytes_and_update_avatar_url(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
    ) -> None:
        owner_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        profile = await creator.execute(CreateProfileInput(user_id=owner_id.value, name="Lucas"))

        use_case = UploadProfileAvatarUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )
        result = await use_case.execute(
            UploadProfileAvatarInput(
                user_id=owner_id.value,
                profile_id=profile.id,
                content=b"fake-bytes",
                declared_mime_type="image/png",
            )
        )

        # Adapter received the upload
        assert fake_avatar_storage.saved == [(profile.id, b"fake-bytes", "image/png")]
        # Profile.avatar_url reflects the URL the adapter returned
        stored = await fake_uow.profiles.find_by_id(ProfileId(profile.id))
        assert stored is not None
        assert stored.avatar_url == result.avatar_url
        assert result.avatar_url is not None
        assert result.avatar_url.startswith(f"/api/v1/profiles/{profile.id}/avatar")

    async def test_should_raise_when_profile_does_not_exist(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
    ) -> None:
        use_case = UploadProfileAvatarUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )

        with pytest.raises(ProfileNotFoundException):
            await use_case.execute(
                UploadProfileAvatarInput(
                    user_id=UserId.generate().value,
                    profile_id=ProfileId.generate().value,
                    content=b"x",
                    declared_mime_type="image/png",
                )
            )
        # Storage was never touched on the early-fail path.
        assert fake_avatar_storage.saved == []

    async def test_should_reject_cross_user_upload(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
    ) -> None:
        owner_id = UserId.generate()
        intruder_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        target = await creator.execute(CreateProfileInput(user_id=owner_id.value, name="Lucas"))

        use_case = UploadProfileAvatarUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )

        with pytest.raises(ProfileOwnershipViolation):
            await use_case.execute(
                UploadProfileAvatarInput(
                    user_id=intruder_id.value,
                    profile_id=target.id,
                    content=b"x",
                    declared_mime_type="image/png",
                )
            )
        # The ownership check runs before the storage call.
        assert fake_avatar_storage.saved == []
