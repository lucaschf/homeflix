"""Integration tests: the parental unlock and its lockout on the real Unit of Work (ADR-035).

``UnlockParentalUseCase`` runs over ``SqlAlchemyIdentityUnitOfWork`` on a
SQLite file configured like the app (``Database``, foreign keys on). What
these tests pin cannot be seen with the in-memory fakes:

- the attempt counter survives the PIN error — the real Unit of Work rolls
  back a transaction left by an exception, the fake does not;
- the reservation is decided by the row ``UPDATE ... RETURNING`` yields,
  whose ``rowcount`` is ``-1`` on this stack;
- the lock length and the ladder are computed by SQL;
- concurrent requests on one device each get their own connection, so
  only an atomic reservation keeps them within the attempt budget, and only
  an atomic consume spends one unlock window once.

Time comes from a controllable clock; the PIN hash from a deterministic,
recording hasher.
"""

import asyncio
import threading
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, select

from src.infrastructure.persistence import Base
from src.infrastructure.persistence.database import Database
from src.modules.identity.application.dtos.identity_dtos import UnlockParentalInput
from src.modules.identity.application.ports import PasswordHasherPort
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
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
)
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyIdentityUnitOfWorkFactory,
)

pytestmark = pytest.mark.integration

_PIN = "904518"
_WRONG_PIN = "111111"
_START = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)
_TV, _TABLET = "token-tv".ljust(43, "0"), "token-tablet".ljust(43, "0")


class _Clock:
    def __init__(self) -> None:
        self.now = _START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class _RecordingHasher(PasswordHasherPort):
    """Deterministic hasher that counts every verification."""

    def __init__(self) -> None:
        self.verify_calls = 0

    def hash(self, password: str) -> str:
        return f"hashed::{password}"

    def verify(self, plain: str, hashed: str) -> bool:
        self.verify_calls += 1
        return hashed == f"hashed::{plain}"


@pytest.fixture
async def database_url(tmp_path: Path) -> str:
    """Create the schema in a fresh SQLite file and return its URL."""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'identity.db').as_posix()}"
    database = Database(url)
    await database.connect()
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await database.disconnect()
    return url


@pytest.fixture
async def database(database_url: str) -> AsyncGenerator[Database, None]:
    """The app's ``Database`` on the SQLite file."""
    db = Database(database_url)
    await db.connect()
    yield db
    await db.disconnect()


@pytest.fixture
def file_uow_factory(database: Database) -> IdentityUnitOfWorkFactory:
    """Identity Unit of Work factory on the SQLite file."""
    return SqlAlchemyIdentityUnitOfWorkFactory(database.session_factory)


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def hasher() -> _RecordingHasher:
    return _RecordingHasher()


@pytest.fixture
async def account(
    file_uow_factory: IdentityUnitOfWorkFactory, database: Database, hasher: _RecordingHasher
) -> User:
    """A user with a parental PIN and two sessions: the TV and the tablet."""
    return await _seed_account(file_uow_factory, database, hasher, pin_hash=hasher.hash(_PIN))


async def _seed_account(
    uow_factory: IdentityUnitOfWorkFactory,
    database: Database,
    hasher: _RecordingHasher,
    *,
    pin_hash: str | None,
) -> User:
    async with uow_factory() as uow:
        user = await uow.users.save(
            User(
                email=Email("parent@example.com"),
                hashed_password=hasher.hash("password"),
                parental_pin_hash=pin_hash,
            )
        )
    async with database.session_factory() as session:
        user_uuid = await session.scalar(
            select(UserModel.id).where(UserModel.external_id == str(user.id))
        )
        # Inserted like the FastAPI Users login: the parental columns come
        # from their server defaults.
        session.add_all(
            [AccessTokenModel(token=token, user_id=user_uuid) for token in (_TV, _TABLET)]
        )
        await session.commit()
    return user


def _use_case(
    uow_factory: IdentityUnitOfWorkFactory, hasher: _RecordingHasher, clock: _Clock
) -> UnlockParentalUseCase:
    return UnlockParentalUseCase(uow_factory=uow_factory, password_hasher=hasher, clock=clock)


def _input(user: User, pin: str, token: str = _TV) -> UnlockParentalInput:
    return UnlockParentalInput(user_id=str(user.id), session_token=token, pin=pin)


async def _state(uow_factory: IdentityUnitOfWorkFactory, token: str = _TV) -> ParentalSessionState:
    async with uow_factory() as uow:
        state = await uow.access_tokens.get_parental_state(token)
    assert state is not None
    return state


async def _wrong(
    use_case: UnlockParentalUseCase, user: User, times: int, token: str = _TV
) -> list[Exception]:
    """Enter a wrong PIN ``times`` times, returning each error raised."""
    errors: list[Exception] = []
    for _ in range(times):
        with pytest.raises((ParentalPinInvalidError, ParentalPinLockedError)) as exc_info:
            await use_case.execute(_input(user, _WRONG_PIN, token))
        errors.append(exc_info.value)
    return errors


async def _lock_seconds_after_five_wrong(use_case: UnlockParentalUseCase, user: User) -> int:
    """Enter five wrong PINs and return how long the lock they start lasts."""
    errors = await _wrong(use_case, user, 5)
    assert [type(e) for e in errors] == [ParentalPinInvalidError] * 4 + [ParentalPinLockedError]
    last = errors[-1]
    assert isinstance(last, ParentalPinLockedError)
    assert last.retry_after_seconds is not None
    return last.retry_after_seconds


class TestAttemptsSurviveTheError:
    async def test_wrong_pin_is_invalid_and_its_attempt_stays_committed(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        with pytest.raises(ParentalPinInvalidError) as exc_info:
            await _use_case(file_uow_factory, hasher, clock).execute(_input(account, _WRONG_PIN))

        assert exc_info.value.code == "PARENTAL_PIN_INVALID"
        assert (await _state(file_uow_factory)).failed_attempts == 1

    async def test_account_without_pin_is_not_configured_and_counts_nothing(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database: Database,
        hasher: _RecordingHasher,
        clock: _Clock,
    ) -> None:
        user = await _seed_account(file_uow_factory, database, hasher, pin_hash=None)

        with pytest.raises(ParentalPinNotConfiguredError):
            await _use_case(file_uow_factory, hasher, clock).execute(_input(user, _PIN))

        assert (await _state(file_uow_factory)).failed_attempts == 0
        assert hasher.verify_calls == 0


class TestUnlock:
    async def test_four_wrong_pins_then_the_right_one_unlocks(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        use_case = _use_case(file_uow_factory, hasher, clock)
        await _wrong(use_case, account, 4)
        assert (await _state(file_uow_factory)).failed_attempts == 4

        await use_case.execute(_input(account, _PIN))

        state = await _state(file_uow_factory)
        assert state.failed_attempts == 0
        assert state.unlock_until is not None
        assert abs((state.unlock_until - (_START + timedelta(seconds=300))).total_seconds()) <= 1

    async def test_right_pin_as_the_fifth_attempt_ends_the_lock_it_started(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        use_case = _use_case(file_uow_factory, hasher, clock)
        await _wrong(use_case, account, 4)

        await use_case.execute(_input(account, _PIN))
        errors = await _wrong(use_case, account, 1)

        assert [type(e) for e in errors] == [ParentalPinInvalidError]


class TestLockout:
    async def test_fifth_wrong_pin_locks_and_the_sixth_is_refused_unchecked(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        use_case = _use_case(file_uow_factory, hasher, clock)
        errors = await _wrong(use_case, account, 4)
        assert [type(e) for e in errors] == [ParentalPinInvalidError] * 4

        with pytest.raises(ParentalPinLockedError) as fifth:
            await use_case.execute(_input(account, _WRONG_PIN))
        clock.advance(seconds=0.4)
        with pytest.raises(ParentalPinLockedError) as sixth:
            await use_case.execute(_input(account, _PIN))

        assert fifth.value.retry_after_seconds == 300
        body = sixth.value.to_dict()
        assert body["code"] == "PARENTAL_PIN_LOCKED"
        assert abs(body["details"][0]["metadata"]["retry_after_seconds"] - 300) <= 1
        assert hasher.verify_calls == 5

    async def test_lock_doubles_on_each_step_of_the_ladder(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        use_case = _use_case(file_uow_factory, hasher, clock)

        first = await _lock_seconds_after_five_wrong(use_case, account)
        clock.advance(seconds=first)
        second = await _lock_seconds_after_five_wrong(use_case, account)
        clock.advance(seconds=second)
        third = await _lock_seconds_after_five_wrong(use_case, account)

        assert (first, second, third) == (300, 600, 1_200)
        assert (await _state(file_uow_factory)).lockouts == 3

    async def test_right_pin_does_not_lower_the_ladder(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        use_case = _use_case(file_uow_factory, hasher, clock)
        clock.advance(seconds=await _lock_seconds_after_five_wrong(use_case, account))

        await _wrong(use_case, account, 2)
        await use_case.execute(_input(account, _PIN))
        next_lock = await _lock_seconds_after_five_wrong(use_case, account)

        assert next_lock == 600

    async def test_ladder_holds_until_a_day_after_the_last_lock_ended(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        use_case = _use_case(file_uow_factory, hasher, clock)
        clock.advance(seconds=await _lock_seconds_after_five_wrong(use_case, account))
        clock.advance(seconds=await _lock_seconds_after_five_wrong(use_case, account))

        clock.advance(hours=24, seconds=-1)
        just_before_decay = await _lock_seconds_after_five_wrong(use_case, account)

        assert just_before_decay == 1_200

    async def test_ladder_decays_a_day_after_the_last_lock_ended(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        use_case = _use_case(file_uow_factory, hasher, clock)
        clock.advance(seconds=await _lock_seconds_after_five_wrong(use_case, account))
        await _wrong(use_case, account, 2)
        await use_case.execute(_input(account, _PIN))
        second = await _lock_seconds_after_five_wrong(use_case, account)
        assert second == 600

        clock.advance(seconds=second)
        clock.advance(hours=24, seconds=1)
        after_decay = await _lock_seconds_after_five_wrong(use_case, account)

        assert after_decay == 300

    async def test_lock_on_the_tablet_leaves_the_tv_free(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        use_case = _use_case(file_uow_factory, hasher, clock)
        await _wrong(use_case, account, 5, token=_TABLET)

        on_tv = await _wrong(use_case, account, 1, token=_TV)
        await use_case.execute(_input(account, _PIN, token=_TV))

        assert [type(e) for e in on_tv] == [ParentalPinInvalidError]
        assert (await _state(file_uow_factory, _TABLET)).locked_until is not None
        assert (await _state(file_uow_factory, _TV)).unlock_until is not None


class TestConcurrentAttempts:
    async def test_ten_simultaneous_wrong_pins_verify_at_most_five(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        use_case = _use_case(file_uow_factory, hasher, clock)

        results = await asyncio.gather(
            *(use_case.execute(_input(account, _WRONG_PIN)) for _ in range(10)),
            return_exceptions=True,
        )

        assert all(isinstance(r, ParentalPinInvalidError | ParentalPinLockedError) for r in results)
        assert hasher.verify_calls <= 5
        state = await _state(file_uow_factory)
        assert state.locked_until is not None
        assert state.locked_until > clock.now
        with pytest.raises(ParentalPinLockedError):
            await use_case.execute(_input(account, _PIN))


class TestConcurrentConsume:
    async def test_two_simultaneous_consumes_spend_one_window_once(
        self,
        database_url: str,
        file_uow_factory: IdentityUnitOfWorkFactory,
        hasher: _RecordingHasher,
        clock: _Clock,
        account: User,
    ) -> None:
        # Two requests, each on its own thread, event loop and connection,
        # held at a barrier right before their UPDATE: whatever each one
        # read before it, the two writes race. Only a consume decided by
        # the UPDATE itself hands the window to exactly one of them.
        await _use_case(file_uow_factory, hasher, clock).execute(_input(account, _PIN))
        barrier = threading.Barrier(2, timeout=5)

        async def consume() -> bool:
            database = Database(database_url)
            await database.connect()

            def wait_before_update(*args: Any) -> None:
                statement: str = args[2]
                if statement.lstrip().upper().startswith("UPDATE"):
                    barrier.wait()

            event.listen(database.engine.sync_engine, "before_cursor_execute", wait_before_update)
            try:
                async with SqlAlchemyIdentityUnitOfWorkFactory(database.session_factory)() as uow:
                    return await uow.access_tokens.consume_unlock(_TV, now=clock.now)
            finally:
                await database.disconnect()

        results = await asyncio.gather(
            *(asyncio.to_thread(asyncio.run, consume()) for _ in range(2))
        )

        assert sorted(results) == [False, True]
        assert (await _state(file_uow_factory)).unlock_until is None
