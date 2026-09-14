"""Unit tests for SwitchProfileUseCase."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    SwitchProfileInput,
)
from src.modules.identity.application.errors import (
    NoActiveSessionError,
    ProfileNotFoundException,
    ProfileOwnershipViolation,
    UserNotFoundException,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.switch_profile import (
    SwitchProfileUseCase,
)
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.errors import ParentalPinRequiredError
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory, seed_account

_NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
_TOKEN = "session-abc"


async def _profile(
    fake_uow: FakeIdentityUnitOfWork, owner: UserId, name: str, limit: int | None
) -> ProfileId:
    saved = await fake_uow.profiles.save(
        Profile(
            user_id=owner,
            name=ProfileName(name),
            maturity_limit=None if limit is None else AgeRating(limit),
        )
    )
    assert saved.id is not None
    return saved.id


def _use_case(factory: FakeIdentityUnitOfWorkFactory) -> SwitchProfileUseCase:
    return SwitchProfileUseCase(uow_factory=factory, clock=lambda: _NOW)


def _switch(owner: UserId, target: ProfileId, token: str = _TOKEN) -> SwitchProfileInput:
    return SwitchProfileInput(
        user_id=owner.value, target_profile_id=target.value, session_token=token
    )


class TestSwitchProfileUseCase:
    async def test_should_set_current_profile_id_on_session_row(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        caller_id = await seed_account(fake_uow_factory)
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
        caller_id = await seed_account(fake_uow_factory)
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
        owner_id = await seed_account(fake_uow_factory)
        intruder_id = await seed_account(fake_uow_factory)
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
        caller_id = await seed_account(fake_uow_factory)
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

    async def test_should_raise_when_the_account_is_gone(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        # The gate reads the caller's account; an unknown one is refused, not
        # read as "no PIN".
        ghost = UserId.generate()
        target = await _profile(fake_uow, ghost, "Target", None)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=ghost)

        with pytest.raises(UserNotFoundException):
            await _use_case(fake_uow_factory).execute(_switch(ghost, target))

        snap = await fake_uow.access_tokens.get_by_token(_TOKEN)
        assert snap is not None
        assert snap.current_profile_id is None


class TestSwitchParentalGate:
    """Amendment 7, decision 9: the switch row, on an account with a PIN."""

    @pytest.fixture
    async def owner(self, fake_uow_factory: FakeIdentityUnitOfWorkFactory) -> UserId:
        return await seed_account(fake_uow_factory, parental_pin_hash="hashed::904518")

    async def _active(self, fake_uow: FakeIdentityUnitOfWork) -> ProfileId | None:
        snap = await fake_uow.access_tokens.get_by_token(_TOKEN)
        assert snap is not None
        return snap.current_profile_id

    async def test_limited_session_entering_an_unrestricted_profile_is_refused_before_the_write(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        # The fake keeps whatever was written before a raise: a switch written
        # before the gate would show here, where a real rollback would hide it.
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=kid)

        with pytest.raises(ParentalPinRequiredError) as exc_info:
            await _use_case(fake_uow_factory).execute(_switch(owner, parent))

        assert exc_info.value.code == "PARENTAL_PIN_REQUIRED"
        assert await self._active(fake_uow) == kid

    async def test_a_valid_unlock_lets_the_switch_through(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(
            token=_TOKEN,
            user_id=owner,
            current_profile_id=kid,
            unlock_until=_NOW + timedelta(minutes=5),
        )
        consume = AsyncMock(wraps=fake_uow.access_tokens.consume_unlock)
        fake_uow.access_tokens.consume_unlock = consume  # type: ignore[method-assign]

        await _use_case(fake_uow_factory).execute(_switch(owner, parent))

        assert await self._active(fake_uow) == parent
        consume.assert_awaited_once_with(_TOKEN, now=_NOW)
        state = await fake_uow.access_tokens.get_parental_state(_TOKEN)
        assert state is not None
        assert state.unlock_until is None

    async def test_an_unlock_ending_now_is_refused(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(
            token=_TOKEN, user_id=owner, current_profile_id=kid, unlock_until=_NOW
        )

        with pytest.raises(ParentalPinRequiredError):
            await _use_case(fake_uow_factory).execute(_switch(owner, parent))

        assert await self._active(fake_uow) == kid

    @pytest.mark.parametrize("target_limit", [12, 10, 0])
    async def test_an_equal_or_lower_limit_needs_no_unlock(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
        target_limit: int,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        sibling = await _profile(fake_uow, owner, "Sibling", target_limit)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=kid)

        await _use_case(fake_uow_factory).execute(_switch(owner, sibling))

        assert await self._active(fake_uow) == sibling

    async def test_ownership_is_checked_before_the_gate(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        stranger = await seed_account(fake_uow_factory)
        strangers_profile = await _profile(fake_uow, stranger, "Stranger", None)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=kid)

        with pytest.raises(ProfileOwnershipViolation):
            await _use_case(fake_uow_factory).execute(_switch(owner, strangers_profile))

    async def test_a_new_session_acts_under_the_lowest_limit_of_the_account(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        # Amendment 7 D1: right after login no profile is selected.
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner)
        use_case = _use_case(fake_uow_factory)

        with pytest.raises(ParentalPinRequiredError):
            await use_case.execute(_switch(owner, parent))
        assert await self._active(fake_uow) is None

        await use_case.execute(_switch(owner, kid))
        assert await self._active(fake_uow) == kid

    async def test_a_session_on_a_deleted_profile_acts_under_age_zero(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        # Read as "no profile selected", the session would get the lowest
        # live limit (10) and enter the 10 freely.
        ten = await _profile(fake_uow, owner, "Ten", 10)
        await _profile(fake_uow, owner, "Parent", None)
        gone = await _profile(fake_uow, owner, "Gone", None)
        await fake_uow.profiles.delete(gone)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=gone)

        with pytest.raises(ParentalPinRequiredError):
            await _use_case(fake_uow_factory).execute(_switch(owner, ten))

        assert await self._active(fake_uow) == gone

    async def test_an_unknown_session_is_refused_with_the_pin_not_401(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        parent = await _profile(fake_uow, owner, "Parent", None)

        with pytest.raises(ParentalPinRequiredError):
            await _use_case(fake_uow_factory).execute(_switch(owner, parent, token="ghost"))


class TestSwitchWithoutAPin:
    async def test_the_gate_is_inert_and_reads_only_the_account(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        owner = await seed_account(fake_uow_factory)
        # A limit cannot exist without a PIN (D2); if one did, it gates nothing.
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=kid)
        state = AsyncMock(wraps=fake_uow.access_tokens.get_parental_state)
        fake_uow.access_tokens.get_parental_state = state  # type: ignore[method-assign]

        await _use_case(fake_uow_factory).execute(_switch(owner, parent))

        state.assert_not_awaited()
        snap = await fake_uow.access_tokens.get_by_token(_TOKEN)
        assert snap is not None
        assert snap.current_profile_id == parent


class TestSwitchRacingALimitChange:
    """The compare-and-set on the target's limit, and its single retry (D9)."""

    @pytest.fixture
    async def owner(self, fake_uow_factory: FakeIdentityUnitOfWorkFactory) -> UserId:
        return await seed_account(fake_uow_factory, parental_pin_hash="hashed::904518")

    def _race(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        change: Callable[[int], Awaitable[None]],
    ) -> list[AgeRating | None]:
        """Run ``change(attempt)`` right before each session write; record what it expected."""
        expected: list[AgeRating | None] = []
        write = fake_uow.access_tokens.update_current_profile

        async def racing(
            token: str, profile_id: ProfileId | None, *, expected_limit: AgeRating | None
        ) -> bool:
            await change(len(expected))
            expected.append(expected_limit)
            return await write(token, profile_id, expected_limit=expected_limit)

        fake_uow.access_tokens.update_current_profile = racing  # type: ignore[method-assign]
        return expected

    async def _relimit(
        self, fake_uow: FakeIdentityUnitOfWork, target: ProfileId, limit: int | None
    ) -> None:
        current = await fake_uow.profiles.find_by_id(target)
        assert current is not None
        assert await fake_uow.profiles.set_maturity_limit(
            target,
            expected=current.maturity_limit,
            new=None if limit is None else AgeRating(limit),
        )

    async def _active(self, fake_uow: FakeIdentityUnitOfWork) -> ProfileId | None:
        snap = await fake_uow.access_tokens.get_by_token(_TOKEN)
        assert snap is not None
        return snap.current_profile_id

    async def test_a_widening_before_the_write_refuses_the_switch_after_one_retry(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        ten = await _profile(fake_uow, owner, "Ten", 10)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=kid)

        async def widen_once(attempt: int) -> None:
            if attempt == 0:
                await self._relimit(fake_uow, ten, None)

        expected = self._race(fake_uow, widen_once)

        with pytest.raises(ParentalPinRequiredError):
            await _use_case(fake_uow_factory).execute(_switch(owner, ten))

        assert expected == [AgeRating(10)]
        assert await self._active(fake_uow) == kid

    async def test_a_narrowing_before_the_write_lets_the_retry_through(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        ten = await _profile(fake_uow, owner, "Ten", 10)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=kid)

        async def narrow_once(attempt: int) -> None:
            if attempt == 0:
                await self._relimit(fake_uow, ten, 8)

        expected = self._race(fake_uow, narrow_once)

        await _use_case(fake_uow_factory).execute(_switch(owner, ten))

        assert expected == [AgeRating(10), AgeRating(8)]
        assert await self._active(fake_uow) == ten

    async def test_a_limit_changing_on_every_attempt_is_refused_after_one_retry(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        ten = await _profile(fake_uow, owner, "Ten", 10)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=kid)

        async def narrow_every_time(attempt: int) -> None:
            await self._relimit(fake_uow, ten, 8 - attempt)

        expected = self._race(fake_uow, narrow_every_time)

        with pytest.raises(ParentalPinRequiredError):
            await _use_case(fake_uow_factory).execute(_switch(owner, ten))

        assert expected == [AgeRating(10), AgeRating(8)]
        assert await self._active(fake_uow) == kid

    async def test_an_unlock_spent_on_the_first_attempt_pays_for_the_retry(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        # The retry is in the same transaction: the window closed by the first
        # attempt is not asked for again.
        kid = await _profile(fake_uow, owner, "Kid", 12)
        teen = await _profile(fake_uow, owner, "Teen", 14)
        fake_uow.access_tokens.seed(
            token=_TOKEN,
            user_id=owner,
            current_profile_id=kid,
            unlock_until=_NOW + timedelta(minutes=5),
        )
        consume = AsyncMock(wraps=fake_uow.access_tokens.consume_unlock)
        fake_uow.access_tokens.consume_unlock = consume  # type: ignore[method-assign]

        async def widen_once(attempt: int) -> None:
            if attempt == 0:
                await self._relimit(fake_uow, teen, 16)

        expected = self._race(fake_uow, widen_once)

        await _use_case(fake_uow_factory).execute(_switch(owner, teen))

        assert expected == [AgeRating(14), AgeRating(16)]
        consume.assert_awaited_once_with(_TOKEN, now=_NOW)
        assert await self._active(fake_uow) == teen

    async def test_a_target_deleted_before_the_write_is_not_found(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        ten = await _profile(fake_uow, owner, "Ten", 10)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=kid)

        async def delete_once(attempt: int) -> None:
            if attempt == 0:
                await fake_uow.profiles.delete(ten)

        self._race(fake_uow, delete_once)

        with pytest.raises(ProfileNotFoundException):
            await _use_case(fake_uow_factory).execute(_switch(owner, ten))

        assert await self._active(fake_uow) == kid
