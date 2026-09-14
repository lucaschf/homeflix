"""Unit tests for UnlockParentalUseCase and LockParentalUseCase (ADR-035, Amendment 7 D4).

The in-memory Unit of Work never discards state on rollback, so these tests
pin the order of the steps and where errors are raised. That a rollback
would hand a counted attempt back is only observable on the real Unit of
Work: see ``tests/modules/identity/integration/application/test_unlock_parental_lockout.py``.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.identity.application.dtos.identity_dtos import (
    LockParentalInput,
    UnlockParentalInput,
)
from src.modules.identity.application.errors import NoActiveSessionError
from src.modules.identity.application.use_cases.lock_parental import LockParentalUseCase
from src.modules.identity.application.use_cases.unlock_parental import (
    UnlockParentalUseCase,
)
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.errors import (
    ParentalPinInvalidError,
    ParentalPinLockedError,
    ParentalPinNotConfiguredError,
)
from src.modules.identity.domain.repositories.access_token_repository import (
    ParentalSessionState,
    PinAttemptReservation,
)
from src.modules.identity.domain.services.parental_gate import LockoutPolicy
from src.modules.identity.domain.value_objects.email import Email
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import (
    FakeIdentityUnitOfWork,
    FakeIdentityUnitOfWorkFactory,
    FakePasswordHasher,
)

pytestmark = pytest.mark.unit

_PIN = "904518"
_WRONG_PIN = "111111"
_TOKEN = "device-token"
_START = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self) -> None:
        self.now = _START

    def __call__(self) -> datetime:
        return self.now


async def _seed(
    fake_uow: FakeIdentityUnitOfWork,
    hasher: FakePasswordHasher,
    *,
    with_pin: bool = True,
) -> User:
    async with fake_uow:
        user = await fake_uow.users.save(
            User(
                email=Email("parent@example.com"),
                hashed_password=hasher.hash("password"),
                parental_pin_hash=hasher.hash(_PIN) if with_pin else None,
            )
        )
    assert user.id is not None
    fake_uow.access_tokens.seed(token=_TOKEN, user_id=user.id)
    return user


async def _state(fake_uow: FakeIdentityUnitOfWork) -> ParentalSessionState:
    state = await fake_uow.access_tokens.get_parental_state(_TOKEN)
    assert state is not None
    return state


def _unlock(
    factory: FakeIdentityUnitOfWorkFactory, hasher: FakePasswordHasher, clock: _Clock
) -> UnlockParentalUseCase:
    return UnlockParentalUseCase(uow_factory=factory, password_hasher=hasher, clock=clock)


def _input(user: User, pin: str = _PIN, token: str = _TOKEN) -> UnlockParentalInput:
    return UnlockParentalInput(user_id=str(user.id), session_token=token, pin=pin)


class TestUnlockParental:
    async def test_correct_pin_opens_a_five_minute_window(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)
        clock = _Clock()

        await _unlock(fake_uow_factory, fake_password_hasher, clock).execute(_input(user))

        state = await _state(fake_uow)
        assert state.unlock_until == _START + timedelta(minutes=5)
        assert state.failed_attempts == 0

    async def test_wrong_pin_is_invalid_and_counted(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)

        with pytest.raises(ParentalPinInvalidError) as exc_info:
            await _unlock(fake_uow_factory, fake_password_hasher, _Clock()).execute(
                _input(user, pin=_WRONG_PIN)
            )

        assert exc_info.value.code == "PARENTAL_PIN_INVALID"
        state = await _state(fake_uow)
        assert state.failed_attempts == 1
        assert state.unlock_until is None

    async def test_fifth_wrong_pin_locks_and_sixth_is_not_verified(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)
        use_case = _unlock(fake_uow_factory, fake_password_hasher, _Clock())
        for _ in range(4):
            with pytest.raises(ParentalPinInvalidError):
                await use_case.execute(_input(user, pin=_WRONG_PIN))

        with pytest.raises(ParentalPinLockedError) as fifth:
            await use_case.execute(_input(user, pin=_WRONG_PIN))
        with pytest.raises(ParentalPinLockedError) as sixth:
            await use_case.execute(_input(user))

        assert fifth.value.retry_after_seconds == 300
        assert sixth.value.retry_after_seconds == 300
        assert sixth.value.to_dict()["details"][0]["metadata"] == {"retry_after_seconds": 300}
        assert len(fake_password_hasher.verify_calls) == 5

    async def test_account_without_pin_is_not_configured_and_counts_nothing(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher, with_pin=False)

        with pytest.raises(ParentalPinNotConfiguredError):
            await _unlock(fake_uow_factory, fake_password_hasher, _Clock()).execute(_input(user))

        assert (await _state(fake_uow)).failed_attempts == 0
        assert fake_password_hasher.verify_calls == []

    @pytest.mark.parametrize("pin", ["12345", "1234567", "12a456", "١٢٣٤٥٦"])
    async def test_malformed_pin_is_rejected_before_counting(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
        pin: str,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)

        with pytest.raises(DomainValidationException) as exc_info:
            await _unlock(fake_uow_factory, fake_password_hasher, _Clock()).execute(
                _input(user, pin=pin)
            )

        assert pin not in str(exc_info.value.to_dict())
        assert (await _state(fake_uow)).failed_attempts == 0
        assert fake_password_hasher.verify_calls == []

    async def test_unknown_token_is_no_active_session(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)

        with pytest.raises(NoActiveSessionError):
            await _unlock(fake_uow_factory, fake_password_hasher, _Clock()).execute(
                _input(user, token="ghost-token")
            )

        assert fake_password_hasher.verify_calls == []

    async def test_token_of_another_user_is_never_counted(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        await _seed(fake_uow, fake_password_hasher)
        stranger = User(id=UserId.generate(), email=Email("stranger@example.com"))

        with pytest.raises(NoActiveSessionError):
            await _unlock(fake_uow_factory, fake_password_hasher, _Clock()).execute(
                _input(stranger, pin=_WRONG_PIN)
            )

        assert (await _state(fake_uow)).failed_attempts == 0


class TestUnlockParentalTransactions:
    async def test_reservation_precedes_a_verification_run_outside_any_transaction(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)
        calls: list[tuple[str, bool]] = []
        tokens, hasher = fake_uow.access_tokens, fake_password_hasher
        reserve, success, verify = (
            tokens.reserve_pin_attempt,
            tokens.record_pin_success,
            hasher.verify,
        )

        async def recording_reserve(
            token: str, *, now: datetime, policy: LockoutPolicy
        ) -> PinAttemptReservation:
            calls.append(("reserve", fake_uow.active))
            return await reserve(token, now=now, policy=policy)

        async def recording_success(token: str, *, now: datetime, unlock_until: datetime) -> None:
            calls.append(("success", fake_uow.active))
            await success(token, now=now, unlock_until=unlock_until)

        def recording_verify(plain: str, hashed: str) -> bool:
            calls.append(("verify", fake_uow.active))
            return verify(plain, hashed)

        monkeypatch.setattr(tokens, "reserve_pin_attempt", recording_reserve)
        monkeypatch.setattr(tokens, "record_pin_success", recording_success)
        monkeypatch.setattr(hasher, "verify", recording_verify)

        await _unlock(fake_uow_factory, hasher, _Clock()).execute(_input(user))

        assert calls == [("reserve", True), ("verify", False), ("success", True)]

    @pytest.mark.parametrize(
        ("wrong_before", "error"),
        [(0, ParentalPinInvalidError), (4, ParentalPinLockedError), (5, ParentalPinLockedError)],
        ids=["invalid", "locking-attempt", "while-locked"],
    )
    async def test_pin_errors_are_raised_after_the_transaction_closed(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
        wrong_before: int,
        error: type[Exception],
    ) -> None:
        # Raised inside the ``async with``, the error would roll back the
        # transaction that counted the attempt.
        user = await _seed(fake_uow, fake_password_hasher)
        use_case = _unlock(fake_uow_factory, fake_password_hasher, _Clock())
        for _ in range(wrong_before):
            with pytest.raises((ParentalPinInvalidError, ParentalPinLockedError)):
                await use_case.execute(_input(user, pin=_WRONG_PIN))
        fake_uow.rolled_back = False

        with pytest.raises(error):
            await use_case.execute(_input(user, pin=_WRONG_PIN))

        assert fake_uow.rolled_back is False


class TestLockParental:
    async def test_closes_only_the_window(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)
        clock = _Clock()
        unlock = _unlock(fake_uow_factory, fake_password_hasher, clock)
        await unlock.execute(_input(user))
        for _ in range(3):
            with pytest.raises(ParentalPinInvalidError):
                await unlock.execute(_input(user, pin=_WRONG_PIN))
        before = await _state(fake_uow)
        assert before.unlock_until is not None

        await LockParentalUseCase(uow_factory=fake_uow_factory).execute(
            LockParentalInput(session_token=_TOKEN)
        )

        after = await _state(fake_uow)
        assert after.unlock_until is None
        assert (after.failed_attempts, after.lockouts, after.locked_until) == (
            before.failed_attempts,
            before.lockouts,
            before.locked_until,
        )

    def test_inputs_keep_secrets_out_of_repr(self) -> None:
        unlock = UnlockParentalInput(user_id="usr_x", session_token="tok-secret", pin=_PIN)
        lock = LockParentalInput(session_token="tok-secret")

        for rendered in (repr(unlock), repr(lock)):
            assert _PIN not in rendered
            assert "tok-secret" not in rendered
