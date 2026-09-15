"""Integration tests: the parental gate on profile operations, on the real Unit of Work (ADR-035).

The switch, create, update and delete use cases run over
``SqlAlchemyIdentityUnitOfWork`` on a SQLite file configured like the app
(``Database``, foreign keys on). What these tests pin cannot be seen with the
in-memory fakes:

- a refused operation leaves the rows as they were once its transaction is
  over — a gate evaluated after the commit would not;
- the unlock is spent in the operation's own transaction, so a write that
  fails after the gate hands the window back;
- two operations racing on one unlock, each on its own connection, cannot
  both spend it;
- a limit changed by another connection between an operation's reads and
  its write is neither bypassed (a switch landing on a widened profile), nor
  written back (a rename restoring the old limit), nor left without a PIN
  (a limit racing the PIN removal).

Every gated operation opens with the account lock, which makes those
interleavings impossible on SQLite (``test_parental_gate_serialization.py``
pins that). The race tests here replace the lock with a plain read of the
account (``without_the_account_lock``), so they keep pinning the
compare-and-sets underneath it, kept as defence in depth.

Order *inside* the transaction (gate before the write) is pinned by the unit
tests: here the rollback would hide a write made before a refusing gate.
"""

import asyncio
import threading
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, select

from src.infrastructure.persistence import Base
from src.infrastructure.persistence.database import Database
from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    DeleteProfileAvatarInput,
    DeleteProfileInput,
    MaturityLimitChange,
    RemoveParentalPinInput,
    SwitchProfileInput,
    UpdateProfileInput,
    UploadProfileAvatarInput,
)
from src.modules.identity.application.ports import AvatarStoragePort, PasswordHasherPort
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases.create_profile import CreateProfileUseCase
from src.modules.identity.application.use_cases.delete_profile import DeleteProfileUseCase
from src.modules.identity.application.use_cases.delete_profile_avatar import (
    DeleteProfileAvatarUseCase,
)
from src.modules.identity.application.use_cases.remove_parental_pin import (
    RemoveParentalPinUseCase,
)
from src.modules.identity.application.use_cases.switch_profile import SwitchProfileUseCase
from src.modules.identity.application.use_cases.update_profile import UpdateProfileUseCase
from src.modules.identity.application.use_cases.upload_profile_avatar import (
    UploadProfileAvatarUseCase,
)
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.errors import (
    ParentalPinInUseError,
    ParentalPinNotConfiguredError,
    ParentalPinRequiredError,
)
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import ProfileModel
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.infrastructure.persistence.repositories.sqlalchemy_profile_repository import (
    SqlAlchemyProfileRepository,
)
from src.modules.identity.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from src.modules.identity.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyIdentityUnitOfWorkFactory,
)
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)
_UNLOCKED = int((_NOW + timedelta(minutes=5)).timestamp())
_TV, _TABLET = "token-tv".ljust(43, "0"), "token-tablet".ljust(43, "0")


class _Account:
    def __init__(self, user_id: UserId, profiles: dict[str, ProfileId]) -> None:
        self.user_id = user_id
        self.profiles = profiles


@pytest.fixture
def without_the_account_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer the account lock like the real one, from a read, without locking.

    With the lock, the concurrent change waits for the held operation, so
    the compare-and-set a test aims at would never see it.
    """

    async def read_only(self: SqlAlchemyUserRepository, user_id: UserId) -> bool:
        return await self.find_by_id(user_id) is not None

    monkeypatch.setattr(SqlAlchemyUserRepository, "lock_for_parental_change", read_only)


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
async def account(file_uow_factory: IdentityUnitOfWorkFactory, database: Database) -> _Account:
    """An account with a PIN and its profiles and sessions.

    Profiles: Parent (unrestricted), Kid (12), A (10) and B (10). Sessions:
    the TV on Parent and the tablet on Kid.
    """
    async with file_uow_factory() as uow:
        user = await uow.users.save(
            User(
                email=Email("parent@example.com"),
                hashed_password="hp",
                parental_pin_hash="hashed::904518",
            )
        )
        assert user.id is not None
        profiles: dict[str, ProfileId] = {}
        for name, limit in (("Parent", None), ("Kid", 12), ("A", 10), ("B", 10)):
            saved = await uow.profiles.save(
                Profile(
                    user_id=user.id,
                    name=ProfileName(name),
                    maturity_limit=None if limit is None else AgeRating(limit),
                )
            )
            assert saved.id is not None
            profiles[name] = saved.id
    async with database.session_factory() as session:
        user_uuid = await session.scalar(
            select(UserModel.id).where(UserModel.external_id == str(user.id))
        )
        session.add_all(
            [
                AccessTokenModel(
                    token=_TV,
                    user_id=user_uuid,
                    current_profile_id=await _profile_uuid(database, profiles["Parent"]),
                ),
                AccessTokenModel(
                    token=_TABLET,
                    user_id=user_uuid,
                    current_profile_id=await _profile_uuid(database, profiles["Kid"]),
                ),
            ]
        )
        await session.commit()
    return _Account(user.id, profiles)


async def _profile_uuid(database: Database, profile_id: ProfileId) -> uuid.UUID:
    async with database.session_factory() as session:
        found = await session.scalar(
            select(ProfileModel.id).where(ProfileModel.external_id == str(profile_id))
        )
    assert found is not None
    return found


async def _token_row(database: Database, token: str) -> tuple[Any, ...]:
    async with database.session_factory() as session:
        result = await session.execute(
            select(
                AccessTokenModel.current_profile_id,
                AccessTokenModel.parental_failed_attempts,
                AccessTokenModel.parental_lockouts,
                AccessTokenModel.parental_locked_until,
                AccessTokenModel.parental_unlock_until,
            ).where(AccessTokenModel.token == token)
        )
        return tuple(result.one())


async def _profile_row(database: Database, profile_id: ProfileId) -> tuple[Any, ...]:
    async with database.session_factory() as session:
        result = await session.execute(
            select(ProfileModel.maturity_limit, ProfileModel.deleted_at).where(
                ProfileModel.external_id == str(profile_id)
            )
        )
        return tuple(result.one())


async def _set_token(database: Database, token: str, **values: Any) -> None:
    async with database.session_factory() as session:
        row = await session.get(AccessTokenModel, token)
        assert row is not None
        for column, value in values.items():
            setattr(row, column, value)
        await session.commit()


def _clock() -> datetime:
    return _NOW


def _widen(account: _Account, name: str, token: str = _TV) -> UpdateProfileInput:
    return UpdateProfileInput(
        user_id=str(account.user_id),
        profile_id=str(account.profiles[name]),
        maturity_limit=MaturityLimitChange(None),
        session_token=token,
    )


class TestRefusedOperationsLeaveTheRows:
    async def test_a_refused_switch_leaves_the_session_row_as_it_was(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database: Database,
        account: _Account,
    ) -> None:
        before = await _token_row(database, _TABLET)

        with pytest.raises(ParentalPinRequiredError):
            await SwitchProfileUseCase(file_uow_factory, clock=_clock).execute(
                SwitchProfileInput(
                    user_id=str(account.user_id),
                    target_profile_id=str(account.profiles["Parent"]),
                    session_token=_TABLET,
                )
            )

        assert await _token_row(database, _TABLET) == before

    async def test_a_refused_widening_leaves_the_profile_and_the_other_sessions(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database: Database,
        account: _Account,
    ) -> None:
        tablet_before = await _token_row(database, _TABLET)

        with pytest.raises(ParentalPinRequiredError):
            await UpdateProfileUseCase(file_uow_factory, clock=_clock).execute(
                _widen(account, "Kid")
            )

        assert (await _profile_row(database, account.profiles["Kid"]))[0] == 12
        assert await _token_row(database, _TABLET) == tablet_before

    async def test_a_refused_creation_saves_no_profile(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database: Database,
        account: _Account,
    ) -> None:
        with pytest.raises(ParentalPinRequiredError):
            await CreateProfileUseCase(file_uow_factory, clock=_clock).execute(
                CreateProfileInput(user_id=str(account.user_id), name="New", session_token=_TABLET)
            )

        async with file_uow_factory() as uow:
            assert len(await uow.profiles.find_by_user(account.user_id)) == 4

    async def test_a_refused_deletion_keeps_the_profile(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database: Database,
        account: _Account,
    ) -> None:
        with pytest.raises(ParentalPinRequiredError):
            await DeleteProfileUseCase(file_uow_factory, _NoAvatars(), clock=_clock).execute(
                DeleteProfileInput(
                    user_id=str(account.user_id),
                    profile_id=str(account.profiles["Kid"]),
                    session_token=_TV,
                )
            )

        assert await _profile_row(database, account.profiles["Kid"]) == (12, None)


class TestWideningWithAnUnlock:
    async def test_spends_the_unlock_and_detaches_the_tablet_in_one_commit(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database: Database,
        account: _Account,
    ) -> None:
        await _set_token(database, _TV, parental_unlock_until=_UNLOCKED)
        tv_profile = (await _token_row(database, _TV))[0]

        output = await UpdateProfileUseCase(file_uow_factory, clock=_clock).execute(
            _widen(account, "Kid")
        )

        assert output.maturity_limit is None
        assert (await _profile_row(database, account.profiles["Kid"]))[0] is None
        assert await _token_row(database, _TV) == (tv_profile, 0, 0, None, None)
        assert await _token_row(database, _TABLET) == (None, 0, 0, None, None)

    async def test_a_write_failing_after_the_gate_hands_the_unlock_back(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database: Database,
        account: _Account,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _set_token(database, _TV, parental_unlock_until=_UNLOCKED)
        tablet_before = await _token_row(database, _TABLET)

        async def failing_save(self: SqlAlchemyProfileRepository, profile: Profile) -> Profile:
            raise RuntimeError("disk full")

        monkeypatch.setattr(SqlAlchemyProfileRepository, "save", failing_save)

        with pytest.raises(RuntimeError, match="disk full"):
            await UpdateProfileUseCase(file_uow_factory, clock=_clock).execute(
                _widen(account, "Kid")
            )

        assert (await _token_row(database, _TV))[4] == _UNLOCKED
        assert await _token_row(database, _TABLET) == tablet_before


@pytest.mark.usefixtures("without_the_account_lock")
class TestConcurrentWidenings:
    async def test_one_unlock_pays_for_exactly_one_of_two_simultaneous_widenings(
        self,
        database_url: str,
        database: Database,
        account: _Account,
    ) -> None:
        # Amendment 7 D9. Two requests from the TV, each on its own thread,
        # event loop and connection, held at a barrier right before their
        # first UPDATE: both have read an open window by then. Only an unlock
        # spent by the UPDATE itself lets exactly one of them through.
        await _set_token(database, _TV, parental_unlock_until=_UNLOCKED)
        barrier = threading.Barrier(2, timeout=5)

        async def widen(name: str) -> str:
            db = Database(database_url)
            await db.connect()
            held = threading.local()

            def wait_before_first_update(*args: Any) -> None:
                statement: str = args[2]
                if statement.lstrip().upper().startswith("UPDATE") and not getattr(
                    held, "done", False
                ):
                    held.done = True
                    barrier.wait()

            event.listen(db.engine.sync_engine, "before_cursor_execute", wait_before_first_update)
            try:
                await UpdateProfileUseCase(
                    SqlAlchemyIdentityUnitOfWorkFactory(db.session_factory), clock=_clock
                ).execute(_widen(account, name))
            except ParentalPinRequiredError:
                return "refused"
            finally:
                await db.disconnect()
            return "widened"

        results = await asyncio.gather(
            asyncio.to_thread(asyncio.run, widen("A")),
            asyncio.to_thread(asyncio.run, widen("B")),
        )

        assert sorted(results) == ["refused", "widened"]
        limits = [(await _profile_row(database, account.profiles[n]))[0] for n in ("A", "B")]
        assert sorted(limits, key=lambda v: v is None) == [10, None]
        assert (await _token_row(database, _TV))[4] is None


class _NoAvatars(AvatarStoragePort):
    """Avatar storage stand-in: a refused deletion never reaches it."""

    async def save(self, profile_id: str, *, content: bytes, declared_mime_type: str) -> str:
        raise AssertionError("not used")

    async def delete(self, profile_id: str) -> None:
        return None


# ─── operations racing a limit change ──────────────────────


@dataclass
class _HeldDevice:
    """An operation running on its own thread, event loop and connection.

    It stops right before the first statement ``hold_at`` accepts, until
    :meth:`finish` lets it go; meanwhile the test commits a change on
    another connection.
    """

    thread: threading.Thread
    reached: threading.Event
    release: threading.Event
    outcome: list[object] = field(default_factory=list)
    statements: list[str] = field(default_factory=list)

    async def wait_until_held(self) -> None:
        assert await asyncio.to_thread(self.reached.wait, 10), "the device never reached the hold"

    async def finish(self) -> object:
        """Let the operation go and return ``"ok"`` or the exception it raised."""
        self.release.set()
        await asyncio.to_thread(self.thread.join, 10)
        assert not self.thread.is_alive()
        assert len(self.outcome) == 1
        return self.outcome[0]


def _held_device(
    database_url: str,
    hold_at: Callable[[str, int], bool],
    operation: Callable[[IdentityUnitOfWorkFactory], Awaitable[object]],
) -> _HeldDevice:
    device = _HeldDevice(
        thread=threading.Thread(target=lambda: asyncio.run(run())),
        reached=threading.Event(),
        release=threading.Event(),
    )

    async def run() -> None:
        db = Database(database_url)
        await db.connect()

        def hold(*args: Any) -> None:
            statement: str = args[2]
            device.statements.append(statement)
            if not device.reached.is_set() and hold_at(statement, len(device.statements)):
                device.reached.set()
                assert device.release.wait(10)

        event.listen(db.engine.sync_engine, "before_cursor_execute", hold)
        try:
            await operation(SqlAlchemyIdentityUnitOfWorkFactory(db.session_factory))
            device.outcome.append("ok")
        except Exception as exc:  # the test inspects what the operation raised
            device.outcome.append(exc)
        finally:
            await db.disconnect()

    device.thread.start()
    return device


def _at_first_write(statement: str, _position: int) -> bool:
    return statement.lstrip().upper().startswith(("UPDATE", "INSERT"))


def _at_statement(position: int) -> Callable[[str, int], bool]:
    return lambda _statement, seen: seen == position


def _switch_to(
    account: _Account, name: str, token: str
) -> Callable[[IdentityUnitOfWorkFactory], Awaitable[object]]:
    async def switch(uow_factory: IdentityUnitOfWorkFactory) -> object:
        await SwitchProfileUseCase(uow_factory, clock=_clock).execute(
            SwitchProfileInput(
                user_id=str(account.user_id),
                target_profile_id=str(account.profiles[name]),
                session_token=token,
            )
        )
        return None

    return switch


def _set_limit(account: _Account, name: str, limit: int | None) -> UpdateProfileInput:
    return UpdateProfileInput(
        user_id=str(account.user_id),
        profile_id=str(account.profiles[name]),
        maturity_limit=MaturityLimitChange(limit),
        session_token=_TV,
    )


async def _limit_and_flag(database: Database, profile_id: ProfileId) -> tuple[Any, ...]:
    async with database.session_factory() as session:
        result = await session.execute(
            select(ProfileModel.maturity_limit, ProfileModel.is_kids).where(
                ProfileModel.external_id == str(profile_id)
            )
        )
        return tuple(result.one())


@pytest.mark.usefixtures("without_the_account_lock")
class TestSwitchRacingALimitChange:
    """Amendment 7 D9: the switch lands only on the limit its gate read."""

    async def test_a_widening_committed_before_the_switch_writes_refuses_it(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database_url: str,
        database: Database,
        account: _Account,
    ) -> None:
        # The tablet (on Kid, 12) enters A (10): allowed as read. Held before
        # its write, the TV widens A; nothing is on A yet, so nothing is
        # detached. Landing on A now would put the tablet on an unrestricted
        # profile without a PIN.
        a_uuid = await _profile_uuid(database, account.profiles["A"])
        tablet = _held_device(database_url, _at_first_write, _switch_to(account, "A", _TABLET))
        await tablet.wait_until_held()

        await _set_token(database, _TV, parental_unlock_until=_UNLOCKED)
        await UpdateProfileUseCase(file_uow_factory, clock=_clock).execute(_widen(account, "A"))
        outcome = await tablet.finish()

        assert (await _profile_row(database, account.profiles["A"]))[0] is None
        assert isinstance(outcome, ParentalPinRequiredError), outcome
        assert (await _token_row(database, _TABLET))[0] != a_uuid

    async def test_a_session_already_on_the_widened_target_is_not_put_back_on_it(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database_url: str,
        database: Database,
        account: _Account,
    ) -> None:
        # The tablet is on A (10) and selects A again. The widening detaches
        # it; the held switch must not attach it back.
        a_uuid = await _profile_uuid(database, account.profiles["A"])
        await _set_token(database, _TABLET, current_profile_id=a_uuid)
        tablet = _held_device(database_url, _at_first_write, _switch_to(account, "A", _TABLET))
        await tablet.wait_until_held()

        await _set_token(database, _TV, parental_unlock_until=_UNLOCKED)
        await UpdateProfileUseCase(file_uow_factory, clock=_clock).execute(_widen(account, "A"))
        outcome = await tablet.finish()

        assert isinstance(outcome, ParentalPinRequiredError), outcome
        assert (await _token_row(database, _TABLET))[0] is None

    async def test_a_narrowing_committed_before_the_switch_writes_lets_it_through_on_the_retry(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database_url: str,
        database: Database,
        account: _Account,
    ) -> None:
        # A narrowed from 10 to 8 still lets the tablet (12) in: the switch
        # notices the change, reads again and writes once more.
        a_uuid = await _profile_uuid(database, account.profiles["A"])
        tablet = _held_device(database_url, _at_first_write, _switch_to(account, "A", _TABLET))
        await tablet.wait_until_held()

        await UpdateProfileUseCase(file_uow_factory, clock=_clock).execute(
            _set_limit(account, "A", 8)
        )
        outcome = await tablet.finish()

        assert outcome == "ok"
        assert (await _token_row(database, _TABLET))[0] == a_uuid
        assert (await _profile_row(database, account.profiles["A"]))[0] == 8
        session_writes = [
            s for s in tablet.statements if s.lstrip().upper().startswith("UPDATE ACCESS_TOKENS")
        ]
        assert len(session_writes) == 2


class _StubAvatars(AvatarStoragePort):
    """Avatar storage stand-in that stores nothing."""

    async def save(self, profile_id: str, *, content: bytes, declared_mime_type: str) -> str:
        return f"/api/v1/profiles/{profile_id}/avatar?v=stub"

    async def delete(self, profile_id: str) -> None:
        return None


def _rename(
    account: _Account, name: str
) -> Callable[[IdentityUnitOfWorkFactory], Awaitable[object]]:
    async def rename(uow_factory: IdentityUnitOfWorkFactory) -> object:
        return await UpdateProfileUseCase(uow_factory, clock=_clock).execute(
            UpdateProfileInput(
                user_id=str(account.user_id),
                profile_id=str(account.profiles[name]),
                name="Renamed",
                session_token=_TABLET,
            )
        )

    return rename


def _upload_avatar(
    account: _Account, name: str
) -> Callable[[IdentityUnitOfWorkFactory], Awaitable[object]]:
    async def upload(uow_factory: IdentityUnitOfWorkFactory) -> object:
        return await UploadProfileAvatarUseCase(uow_factory, _StubAvatars()).execute(
            UploadProfileAvatarInput(
                user_id=str(account.user_id),
                profile_id=str(account.profiles[name]),
                content=b"png",
                declared_mime_type="image/png",
            )
        )

    return upload


def _delete_avatar(
    account: _Account, name: str
) -> Callable[[IdentityUnitOfWorkFactory], Awaitable[object]]:
    async def delete(uow_factory: IdentityUnitOfWorkFactory) -> object:
        return await DeleteProfileAvatarUseCase(uow_factory, _StubAvatars()).execute(
            DeleteProfileAvatarInput(
                user_id=str(account.user_id), profile_id=str(account.profiles[name])
            )
        )

    return delete


# Each operation is held right after it has read the profile it will save: the
# rename after the account lock's read and its profile read, the upload after
# the re-read of its second transaction, the avatar removal after its only read.
_WRITES_OF_OTHER_FIELDS = {
    "rename": (_rename, 3),
    "avatar-upload": (_upload_avatar, 3),
    "avatar-delete": (_delete_avatar, 2),
}


@pytest.mark.usefixtures("without_the_account_lock")
class TestOtherFieldsRacingALimitChange:
    """ADR-035: writing other fields never restores a limit changed after the read."""

    @pytest.mark.parametrize(
        ("name", "narrowed", "kids"),
        [("Kid", 10, True), ("Parent", 12, True)],
        ids=["kid-12-to-10", "parent-none-to-12"],
    )
    @pytest.mark.parametrize("operation", sorted(_WRITES_OF_OTHER_FIELDS))
    async def test_the_limit_committed_meanwhile_survives(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database_url: str,
        database: Database,
        account: _Account,
        operation: str,
        name: str,
        narrowed: int,
        kids: bool,
    ) -> None:
        build, hold_position = _WRITES_OF_OTHER_FIELDS[operation]
        tablet = _held_device(database_url, _at_statement(hold_position), build(account, name))
        await tablet.wait_until_held()

        # The parent, on the TV (Parent, unrestricted), narrows the profile:
        # no unlock needed.
        narrowing = await UpdateProfileUseCase(file_uow_factory, clock=_clock).execute(
            _set_limit(account, name, narrowed)
        )
        outcome = await tablet.finish()

        assert narrowing.maturity_limit == narrowed
        assert not isinstance(outcome, Exception), outcome
        assert await _limit_and_flag(database, account.profiles[name]) == (narrowed, kids)


_PASSWORD = "correct-horse"


class _TaggingHasher(PasswordHasherPort):
    """Reversible stand-in hasher: ``hashed::<plain>``."""

    def hash(self, password: str) -> str:
        return f"hashed::{password}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"hashed::{plain}"


@pytest.fixture
async def unlimited_account(
    file_uow_factory: IdentityUnitOfWorkFactory, database: Database
) -> _Account:
    """An account with a PIN and no limit yet: Parent and Kid, the TV on Parent."""
    async with file_uow_factory() as uow:
        user = await uow.users.save(
            User(
                email=Email("household@example.com"),
                hashed_password=f"hashed::{_PASSWORD}",
                parental_pin_hash="hashed::904518",
            )
        )
        assert user.id is not None
        profiles: dict[str, ProfileId] = {}
        for name in ("Parent", "Kid"):
            saved = await uow.profiles.save(Profile(user_id=user.id, name=ProfileName(name)))
            assert saved.id is not None
            profiles[name] = saved.id
    async with database.session_factory() as session:
        user_uuid = await session.scalar(
            select(UserModel.id).where(UserModel.external_id == str(user.id))
        )
        session.add(
            AccessTokenModel(
                token=_TV,
                user_id=user_uuid,
                current_profile_id=await _profile_uuid(database, profiles["Parent"]),
            )
        )
        await session.commit()
    return _Account(user.id, profiles)


async def _pin_and_live_limits(database: Database, account: _Account) -> tuple[Any, list[Any]]:
    async with database.session_factory() as session:
        user_uuid, pin_hash = (
            await session.execute(
                select(UserModel.id, UserModel.parental_pin_hash).where(
                    UserModel.external_id == str(account.user_id)
                )
            )
        ).one()
        limits = (
            await session.scalars(
                select(ProfileModel.maturity_limit).where(
                    ProfileModel.user_id == user_uuid,
                    ProfileModel.deleted_at.is_(None),
                    ProfileModel.maturity_limit.is_not(None),
                )
            )
        ).all()
    return pin_hash, list(limits)


def _put_limit(account: _Account) -> Callable[[IdentityUnitOfWorkFactory], Awaitable[object]]:
    async def put(uow_factory: IdentityUnitOfWorkFactory) -> object:
        return await UpdateProfileUseCase(uow_factory, clock=_clock).execute(
            _set_limit(account, "Kid", 12)
        )

    return put


def _post_limited(account: _Account) -> Callable[[IdentityUnitOfWorkFactory], Awaitable[object]]:
    async def post(uow_factory: IdentityUnitOfWorkFactory) -> object:
        return await CreateProfileUseCase(uow_factory, clock=_clock).execute(
            CreateProfileInput(
                user_id=str(account.user_id), name="New", maturity_limit=12, session_token=_TV
            )
        )

    return post


def _remove_pin(account: _Account) -> Callable[[IdentityUnitOfWorkFactory], Awaitable[object]]:
    async def remove(uow_factory: IdentityUnitOfWorkFactory) -> object:
        await RemoveParentalPinUseCase(uow_factory, _TaggingHasher()).execute(
            RemoveParentalPinInput(user_id=str(account.user_id), current_password=_PASSWORD)
        )
        return None

    return remove


_LIMIT_WRITES = {"put": _put_limit, "post": _post_limited}


@pytest.mark.usefixtures("without_the_account_lock")
class TestLimitRacingThePinRemoval:
    """Amendment 7 D2: whichever commits first, no limit is left without a PIN."""

    @pytest.mark.parametrize("write", sorted(_LIMIT_WRITES))
    async def test_a_pin_removed_before_the_limit_is_written_refuses_the_limit(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database_url: str,
        database: Database,
        unlimited_account: _Account,
        write: str,
    ) -> None:
        # The limit write read the PIN and is held before writing; the PIN
        # removal finds no limit and commits.
        device = _held_device(
            database_url, _at_first_write, _LIMIT_WRITES[write](unlimited_account)
        )
        await device.wait_until_held()

        await _remove_pin(unlimited_account)(file_uow_factory)
        outcome = await device.finish()

        assert await _pin_and_live_limits(database, unlimited_account) == (None, [])
        assert isinstance(outcome, ParentalPinNotConfiguredError), outcome

    @pytest.mark.parametrize("write", sorted(_LIMIT_WRITES))
    async def test_a_limit_written_before_the_pin_is_removed_keeps_the_pin(
        self,
        file_uow_factory: IdentityUnitOfWorkFactory,
        database_url: str,
        database: Database,
        unlimited_account: _Account,
        write: str,
    ) -> None:
        # The PIN removal checked the password and is held before writing;
        # the limit is written and committed.
        device = _held_device(database_url, _at_first_write, _remove_pin(unlimited_account))
        await device.wait_until_held()

        await _LIMIT_WRITES[write](unlimited_account)(file_uow_factory)
        outcome = await device.finish()

        assert await _pin_and_live_limits(database, unlimited_account) == ("hashed::904518", [12])
        assert isinstance(outcome, ParentalPinInUseError), outcome
