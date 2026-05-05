"""Unit tests for GetActiveProfileForSessionUseCase."""

from src.modules.identity.application.use_cases.get_active_profile_for_session import (
    GetActiveProfileForSessionUseCase,
)
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory


class TestGetActiveProfileForSessionUseCase:
    async def test_should_return_none_when_token_is_unknown(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        use_case = GetActiveProfileForSessionUseCase(uow_factory=fake_uow_factory)

        result = await use_case.execute("ghost-token")

        assert result is None

    async def test_should_return_none_when_session_has_no_active_profile(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        token = "session-abc"
        fake_uow.access_tokens.seed(token=token, user_id=UserId.generate())
        use_case = GetActiveProfileForSessionUseCase(uow_factory=fake_uow_factory)

        result = await use_case.execute(token)

        assert result is None

    async def test_should_return_external_profile_id_when_one_is_set(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        token = "session-abc"
        active = ProfileId.generate()
        fake_uow.access_tokens.seed(
            token=token,
            user_id=UserId.generate(),
            current_profile_id=active,
        )
        use_case = GetActiveProfileForSessionUseCase(uow_factory=fake_uow_factory)

        result = await use_case.execute(token)

        assert result == active.value
