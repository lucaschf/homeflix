"""Unit tests for ListProfilesForUserUseCase."""

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    ListProfilesForUserInput,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.list_profiles_for_user import (
    ListProfilesForUserUseCase,
)
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWorkFactory


class TestListProfilesForUserUseCase:
    async def test_should_return_empty_list_when_user_has_no_profiles(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ):
        use_case = ListProfilesForUserUseCase(uow_factory=fake_uow_factory)

        output = await use_case.execute(ListProfilesForUserInput(user_id=UserId.generate().value))

        assert output == []

    async def test_should_return_profiles_ordered_by_name(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ):
        caller_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        for name in ("Charlie", "Alice", "Bob"):
            await creator.execute(CreateProfileInput(user_id=caller_id.value, name=name))

        use_case = ListProfilesForUserUseCase(uow_factory=fake_uow_factory)
        output = await use_case.execute(ListProfilesForUserInput(user_id=caller_id.value))

        assert [p.name for p in output] == ["Alice", "Bob", "Charlie"]

    async def test_should_isolate_profiles_by_caller(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ):
        alice = UserId.generate()
        bob = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        await creator.execute(CreateProfileInput(user_id=alice.value, name="Alice's"))
        await creator.execute(CreateProfileInput(user_id=alice.value, name="Alice's Kids"))
        await creator.execute(CreateProfileInput(user_id=bob.value, name="Bob's"))

        use_case = ListProfilesForUserUseCase(uow_factory=fake_uow_factory)
        alice_view = await use_case.execute(ListProfilesForUserInput(user_id=alice.value))
        bob_view = await use_case.execute(ListProfilesForUserInput(user_id=bob.value))

        assert {p.name for p in alice_view} == {"Alice's", "Alice's Kids"}
        assert {p.name for p in bob_view} == {"Bob's"}
