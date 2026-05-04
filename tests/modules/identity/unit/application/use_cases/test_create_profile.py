"""Unit tests for CreateProfileUseCase."""

from src.modules.identity.application.dtos.identity_dtos import CreateProfileInput
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory


class TestCreateProfileUseCase:
    async def test_should_persist_profile_owned_by_caller(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        caller_id = UserId.generate()
        use_case = CreateProfileUseCase(uow_factory=fake_uow_factory)

        output = await use_case.execute(
            CreateProfileInput(
                user_id=caller_id.value,
                name="Lucas",
            )
        )

        assert output.id.startswith("prf_")
        assert output.user_id == caller_id.value
        assert output.name == "Lucas"
        assert output.is_kids is False
        assert output.avatar_url is None
        # Repository was actually written through:
        assert await fake_uow.profiles.count_for_user(caller_id) == 1

    async def test_should_propagate_kids_flag_and_avatar_url(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        caller_id = UserId.generate()
        use_case = CreateProfileUseCase(uow_factory=fake_uow_factory)

        output = await use_case.execute(
            CreateProfileInput(
                user_id=caller_id.value,
                name="Bia",
                is_kids=True,
                avatar_url="https://example.com/bia.png",
            )
        )

        assert output.is_kids is True
        assert output.avatar_url == "https://example.com/bia.png"

    async def test_should_assign_distinct_external_ids_to_multiple_profiles(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        caller_id = UserId.generate()
        use_case = CreateProfileUseCase(uow_factory=fake_uow_factory)

        a = await use_case.execute(CreateProfileInput(user_id=caller_id.value, name="Alice"))
        b = await use_case.execute(CreateProfileInput(user_id=caller_id.value, name="Bob"))

        assert a.id != b.id
