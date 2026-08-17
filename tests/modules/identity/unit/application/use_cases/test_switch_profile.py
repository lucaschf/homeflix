"""Unit tests for SwitchProfileUseCase."""

import pytest

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    SwitchProfileInput,
)
from src.modules.identity.application.errors import (
    NoActiveSessionError,
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.switch_profile import (
    SwitchProfileUseCase,
)
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory


class TestSwitchProfileUseCase:
    async def test_should_set_current_profile_id_on_session_row(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        caller_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        target = await creator.execute(CreateProfileInput(user_id=caller_id.value, name="Target"))
        token = "session-abc"
        fake_uow.access_tokens.seed(token=token, user_id=caller_id)

        use_case = SwitchProfileUseCase(uow_factory=fake_uow_factory)
        await use_case.execute(
            SwitchProfileInput(
                user_id=caller_id.value,
                target_profile_id=target.id,
                session_token=token,
            )
        )

        snap = await fake_uow.access_tokens.get_by_token(token)
        assert snap is not None
        assert snap.current_profile_id == ProfileId(target.id)

    async def test_should_raise_when_target_profile_does_not_exist(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        caller_id = UserId.generate()
        token = "session-abc"
        fake_uow.access_tokens.seed(token=token, user_id=caller_id)

        use_case = SwitchProfileUseCase(uow_factory=fake_uow_factory)

        with pytest.raises(ProfileNotFoundException):
            await use_case.execute(
                SwitchProfileInput(
                    user_id=caller_id.value,
                    target_profile_id=ProfileId.generate().value,
                    session_token=token,
                )
            )

    async def test_should_raise_when_caller_does_not_own_target(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        owner_id = UserId.generate()
        intruder_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        target = await creator.execute(CreateProfileInput(user_id=owner_id.value, name="Owners"))
        token = "session-abc"
        fake_uow.access_tokens.seed(token=token, user_id=intruder_id)

        use_case = SwitchProfileUseCase(uow_factory=fake_uow_factory)

        with pytest.raises(ProfileOwnershipViolation):
            await use_case.execute(
                SwitchProfileInput(
                    user_id=intruder_id.value,
                    target_profile_id=target.id,
                    session_token=token,
                )
            )

    async def test_should_raise_when_session_token_is_unknown(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        caller_id = UserId.generate()
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        target = await creator.execute(CreateProfileInput(user_id=caller_id.value, name="Target"))

        use_case = SwitchProfileUseCase(uow_factory=fake_uow_factory)

        with pytest.raises(NoActiveSessionError):
            await use_case.execute(
                SwitchProfileInput(
                    user_id=caller_id.value,
                    target_profile_id=target.id,
                    session_token="ghost-token",
                )
            )
