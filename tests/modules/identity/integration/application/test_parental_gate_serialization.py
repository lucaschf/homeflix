"""Integration tests: parental changes of one account never interleave (ADR-035, Amendment 7).

Each request runs as it does in the app, on its own thread, event loop,
``Database`` and connection over one SQLite file, and can be held right
before a chosen statement while another request runs. What they pin:

- **The account lock.** Every gated profile operation, and the write of
  setting or removing the PIN, opens its Unit of Work with
  ``UserRepository.lock_for_parental_change``. A second one waits until the
  first commits, so a gate never mixes a session read before a concurrent
  widening with profiles read after it, and the PIN it read is still the PIN
  when its change lands.
- **No resurrection.** Saving a profile read before a concurrent delete
  answers not found instead of restoring it — with its limit, possibly after
  the PIN that protected it was removed.
- **One snapshot for the admin gate.** The admin check takes no lock; it
  reads the session and the profiles in one statement, so a widening has no
  statement boundary to commit into.

Each race also has a serial reading: the outcome and the rows must be ones
the two requests produce one after the other, in some order.
"""

import asyncio
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, select

from src.infrastructure.persistence import Base
from src.infrastructure.persistence.database import Database
from src.modules.identity.application.dtos.identity_dtos import (
    AdminAccessLevel,
    CreateProfileInput,
    DeleteProfileAvatarInput,
    DeleteProfileInput,
    GetAdminAccessInput,
    MaturityLimitChange,
    RemoveParentalPinInput,
    SetParentalPinInput,
    SwitchProfileInput,
    UpdateProfileInput,
    UploadProfileAvatarInput,
)
from src.modules.identity.application.errors import ProfileNotFoundException
from src.modules.identity.application.ports import AvatarStoragePort, PasswordHasherPort
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases.create_profile import CreateProfileUseCase
from src.modules.identity.application.use_cases.delete_profile import DeleteProfileUseCase
from src.modules.identity.application.use_cases.delete_profile_avatar import (
    DeleteProfileAvatarUseCase,
)
from src.modules.identity.application.use_cases.get_admin_access import GetAdminAccessUseCase
from src.modules.identity.application.use_cases.remove_parental_pin import (
    RemoveParentalPinUseCase,
)
from src.modules.identity.application.use_cases.set_parental_pin import SetParentalPinUseCase
from src.modules.identity.application.use_cases.switch_profile import SwitchProfileUseCase
from src.modules.identity.application.use_cases.update_profile import UpdateProfileUseCase
from src.modules.identity.application.use_cases.upload_profile_avatar import (
    UploadProfileAvatarUseCase,
)
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.errors import ParentalPinRequiredError
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import ProfileModel
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyIdentityUnitOfWorkFactory,
)
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)
_UNLOCKED = int((_NOW + timedelta(minutes=5)).timestamp())
_PASSWORD = "correct-horse"
_PIN = "904518"
_TV, _TABLET, _PHONE = (name.ljust(43, "0") for name in ("token-tv", "token-tablet", "token-phone"))
_SEEDED_AVATAR = "/api/v1/profiles/seeded/avatar?v=seed"

# A request still inside one statement after this long is waiting for a lock.
_BLOCKED_AFTER_SECONDS = 0.5

Operation = Callable[[IdentityUnitOfWorkFactory], Awaitable[object]]
Hold = Callable[[str, list[str]], bool]
"""Whether to hold before ``statement``, given the statements the request already sent."""


def _clock() -> datetime:
    return _NOW


class _TaggingHasher(PasswordHasherPort):
    """Reversible stand-in hasher: ``hashed::<plain>``."""

    def hash(self, password: str) -> str:
        return f"hashed::{password}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"hashed::{plain}"


class _StubAvatars(AvatarStoragePort):
    """Avatar storage stand-in that stores nothing."""

    async def save(self, profile_id: str, *, content: bytes, declared_mime_type: str) -> str:
        return f"/api/v1/profiles/{profile_id}/avatar?v=stub"

    async def delete(self, profile_id: str) -> None:
        return None


# ─── the household ─────────────────────────────────────────


@dataclass(frozen=True)
class _Household:
    """An account with a PIN, its profiles by name and its sessions by token."""

    path: Path
    user_id: UserId
    profiles: dict[str, ProfileId]

    @property
    def url(self) -> str:
        return f"sqlite+aiosqlite:///{self.path.as_posix()}"

    def profile(self, name: str) -> str:
        return str(self.profiles[name])

    def rows(self) -> "_Rows":
        """Read the account as it is now, through a plain connection.

        Profiles are named as seeded, whatever a rename stored; a profile
        created meanwhile goes by its stored name.
        """
        seeded = {str(profile_id): name for name, profile_id in self.profiles.items()}
        conn = sqlite3.connect(self.path)
        try:
            pin = conn.execute("SELECT parental_pin_hash FROM users").fetchone()[0]
            profiles = {
                seeded.get(external_id, name): (limit, deleted is None)
                for external_id, name, limit, deleted in conn.execute(
                    "SELECT external_id, name, maturity_limit, deleted_at FROM profiles"
                )
            }
            sessions = {
                token: None if external_id is None else seeded.get(external_id, external_id)
                for token, external_id in conn.execute(
                    "SELECT t.token, p.external_id FROM access_tokens t "
                    "LEFT JOIN profiles p ON p.id = t.current_profile_id"
                )
            }
        finally:
            conn.close()
        return _Rows(pin=pin, profiles=profiles, sessions=sessions)


@dataclass(frozen=True)
class _Rows:
    pin: str | None
    profiles: dict[str, tuple[int | None, bool]]  # name -> (limit, live)
    sessions: dict[str, str | None]  # token -> seeded name of the selected profile

    def live_limits(self) -> dict[str, int]:
        return {
            name: limit
            for name, (limit, live) in self.profiles.items()
            if live and limit is not None
        }

    def is_live(self, name: str) -> bool:
        return self.profiles[name][1]


_STANDARD = {"Parent": None, "Kid": 12, "A": 10, "B": 10, "K14": 14}
_SOLO = {"Parent": None, "Kid": 12, "Free": None}


async def _household(
    tmp_path: Path,
    profiles: dict[str, int | None],
    sessions: dict[str, tuple[str, bool]],
    *,
    avatar_on: str | None = None,
) -> _Household:
    """Build the account; ``sessions`` maps a token to (profile name, unlocked)."""
    path = tmp_path / "household.db"
    db = Database(f"sqlite+aiosqlite:///{path.as_posix()}")
    await db.connect()
    try:
        async with db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with SqlAlchemyIdentityUnitOfWorkFactory(db.session_factory)() as uow:
            user = await uow.users.save(
                User(
                    email=Email("parent@example.com"),
                    hashed_password=f"hashed::{_PASSWORD}",
                    parental_pin_hash=f"hashed::{_PIN}",
                )
            )
            assert user.id is not None
            ids: dict[str, ProfileId] = {}
            for name, limit in profiles.items():
                saved = await uow.profiles.save(
                    Profile(
                        user_id=user.id,
                        name=ProfileName(name),
                        maturity_limit=None if limit is None else AgeRating(limit),
                        avatar_url=_SEEDED_AVATAR if name == avatar_on else None,
                    )
                )
                assert saved.id is not None
                ids[name] = saved.id
        async with db.session_factory() as session:
            user_uuid = await session.scalar(
                select(UserModel.id).where(UserModel.external_id == str(user.id))
            )
            for token, (on, unlocked) in sessions.items():
                session.add(
                    AccessTokenModel(
                        token=token,
                        user_id=user_uuid,
                        current_profile_id=await session.scalar(
                            select(ProfileModel.id).where(ProfileModel.external_id == str(ids[on]))
                        ),
                        parental_unlock_until=_UNLOCKED if unlocked else None,
                    )
                )
            await session.commit()
    finally:
        await db.disconnect()
    return _Household(path=path, user_id=user.id, profiles=ids)


# ─── operations ────────────────────────────────────────────

_UNSET: Any = object()


def _switch(home: _Household, token: str, target: str) -> Operation:
    async def run(uow_factory: IdentityUnitOfWorkFactory) -> object:
        await SwitchProfileUseCase(uow_factory, clock=_clock).execute(
            SwitchProfileInput(
                user_id=str(home.user_id),
                target_profile_id=home.profile(target),
                session_token=token,
            )
        )
        return None

    return run


def _put(
    home: _Household,
    token: str,
    target: str,
    *,
    limit: Any = _UNSET,
    name: str | None = None,
    libraries: list[str] | None = None,
) -> Operation:
    async def run(uow_factory: IdentityUnitOfWorkFactory) -> object:
        return await UpdateProfileUseCase(uow_factory, clock=_clock).execute(
            UpdateProfileInput(
                user_id=str(home.user_id),
                profile_id=home.profile(target),
                name=name,
                allowed_library_ids=libraries,
                maturity_limit=None if limit is _UNSET else MaturityLimitChange(limit),
                session_token=token,
            )
        )

    return run


def _create(home: _Household, token: str, name: str, limit: int | None) -> Operation:
    async def run(uow_factory: IdentityUnitOfWorkFactory) -> object:
        return await CreateProfileUseCase(uow_factory, clock=_clock).execute(
            CreateProfileInput(
                user_id=str(home.user_id), name=name, maturity_limit=limit, session_token=token
            )
        )

    return run


def _delete(home: _Household, token: str, target: str) -> Operation:
    async def run(uow_factory: IdentityUnitOfWorkFactory) -> object:
        await DeleteProfileUseCase(uow_factory, _StubAvatars(), clock=_clock).execute(
            DeleteProfileInput(
                user_id=str(home.user_id), profile_id=home.profile(target), session_token=token
            )
        )
        return None

    return run


def _upload_avatar(home: _Household, target: str) -> Operation:
    async def run(uow_factory: IdentityUnitOfWorkFactory) -> object:
        return await UploadProfileAvatarUseCase(uow_factory, _StubAvatars()).execute(
            UploadProfileAvatarInput(
                user_id=str(home.user_id),
                profile_id=home.profile(target),
                content=b"png",
                declared_mime_type="image/png",
            )
        )

    return run


def _delete_avatar(home: _Household, target: str) -> Operation:
    async def run(uow_factory: IdentityUnitOfWorkFactory) -> object:
        return await DeleteProfileAvatarUseCase(uow_factory, _StubAvatars()).execute(
            DeleteProfileAvatarInput(user_id=str(home.user_id), profile_id=home.profile(target))
        )

    return run


def _remove_pin(home: _Household) -> Operation:
    async def run(uow_factory: IdentityUnitOfWorkFactory) -> object:
        await RemoveParentalPinUseCase(uow_factory, _TaggingHasher()).execute(
            RemoveParentalPinInput(user_id=str(home.user_id), current_password=_PASSWORD)
        )
        return None

    return run


def _set_pin(home: _Household) -> Operation:
    async def run(uow_factory: IdentityUnitOfWorkFactory) -> object:
        await SetParentalPinUseCase(uow_factory, _TaggingHasher()).execute(
            SetParentalPinInput(user_id=str(home.user_id), current_password=_PASSWORD, pin=_PIN)
        )
        return None

    return run


def _admin_read(home: _Household, token: str) -> Operation:
    async def run(uow_factory: IdentityUnitOfWorkFactory) -> object:
        return await GetAdminAccessUseCase(uow_factory, clock=_clock).execute(
            GetAdminAccessInput(
                user_id=str(home.user_id),
                role=UserRole.ADMIN,
                parental_pin_configured=True,
                session_token=token,
                is_write=False,
            )
        )

    return run


def _in_order(*operations: Operation) -> Operation:
    """Run ``operations`` one after the other on the same device, stopping at an error."""

    async def run(uow_factory: IdentityUnitOfWorkFactory) -> object:
        for operation in operations:
            await operation(uow_factory)
        return None

    return run


# ─── devices ───────────────────────────────────────────────


class _Timeline:
    """What every device did, in one order across their threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.events: list[tuple[str, str]] = []

    def add(self, device: str, what: str) -> None:
        with self._lock:
            self.events.append((device, what))

    def index(self, device: str, predicate: Callable[[str], bool]) -> int:
        with self._lock:
            return next(
                i for i, (who, what) in enumerate(self.events) if who == device and predicate(what)
            )


@dataclass
class _Device:
    """One request on its own thread, event loop, ``Database`` and connection."""

    name: str
    holds: tuple[Hold, ...]
    timeline: _Timeline
    statements: list[str] = field(default_factory=list)
    outcome: object = None
    in_statement_since: float | None = None
    done: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.reached = [threading.Event() for _ in self.holds]
        self.release = [threading.Event() for _ in self.holds]

    async def reached_hold(self, index: int) -> bool:
        """Wait until the device stops at hold ``index``; ``False`` if it finished first."""

        def poll() -> bool:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if self.reached[index].is_set():
                    return True
                if self.done.is_set():
                    return False
                time.sleep(0.005)
            raise AssertionError(f"{self.name} neither reached hold {index} nor finished")

        return await asyncio.to_thread(poll)

    async def finished_or_blocked(self) -> str:
        """Wait until the device finishes or waits inside a statement for a lock."""

        def poll() -> str:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if self.done.is_set():
                    return "finished"
                since = self.in_statement_since
                if since is not None and time.monotonic() - since >= _BLOCKED_AFTER_SECONDS:
                    return "blocked"
                time.sleep(0.005)
            raise AssertionError(f"{self.name} neither finished nor blocked")

        return await asyncio.to_thread(poll)

    async def finish(self) -> object:
        """Release every hold and return ``"ok"``, the result or the exception raised."""
        for release in self.release:
            release.set()
        assert await asyncio.to_thread(self.done.wait, 30), f"{self.name} never finished"
        return self.outcome


def _start(
    home: _Household,
    operation: Operation,
    *,
    name: str,
    timeline: _Timeline,
    holds: tuple[Hold, ...] = (),
) -> _Device:
    device = _Device(name=name, holds=holds, timeline=timeline)

    async def run() -> None:
        db = Database(home.url)
        await db.connect()
        engine = db.engine.sync_engine
        passed = 0

        def before(*args: Any) -> None:
            nonlocal passed
            statement = " ".join(args[2].split())
            if passed < len(holds) and holds[passed](statement, device.statements):
                device.reached[passed].set()
                assert device.release[passed].wait(30), "hold never released"
                passed += 1
            device.statements.append(statement)
            device.in_statement_since = time.monotonic()

        def after(*args: Any) -> None:
            device.in_statement_since = None
            timeline.add(name, f"ran {device.statements[-1]}")

        event.listen(engine, "before_cursor_execute", before)
        event.listen(engine, "after_cursor_execute", after)
        event.listen(engine, "commit", lambda *args: timeline.add(name, "COMMIT"))
        try:
            result = await operation(SqlAlchemyIdentityUnitOfWorkFactory(db.session_factory))
            device.outcome = "ok" if result is None else result
        except Exception as exc:  # the test inspects what the request raised
            device.outcome = exc
        finally:
            await db.disconnect()
            device.done.set()

    threading.Thread(target=lambda: asyncio.run(run()), daemon=True).start()
    return device


@dataclass(frozen=True)
class _Race:
    victim: object
    attacker: object
    attacker_meanwhile: str  # "finished" or "blocked", while the victim was held


async def _race(home: _Household, victim: Operation, hold: Hold, attacker: Operation) -> _Race:
    """Hold ``victim`` before a statement, run ``attacker`` meanwhile, then let both finish.

    The attacker runs to its end, or until it waits for a lock the victim
    holds; only then is the victim released.
    """
    timeline = _Timeline()
    held = _start(home, victim, name="victim", timeline=timeline, holds=(hold,))
    assert await held.reached_hold(0), f"the victim never reached the hold: {held.statements}"
    free = _start(home, attacker, name="attacker", timeline=timeline)
    meanwhile = await free.finished_or_blocked()
    return _Race(
        victim=await held.finish(), attacker=await free.finish(), attacker_meanwhile=meanwhile
    )


# ─── holds ─────────────────────────────────────────────────


def _before_the_account_profiles_read(statement: str, _sent: list[str]) -> bool:
    """The read of every live profile of the account, which the gate makes last."""
    return statement.startswith("SELECT") and statement.endswith("ORDER BY profiles.name")


def _before_the_account_read(statement: str, _sent: list[str]) -> bool:
    """The read of the caller's account, where the gate learns whether it has a PIN."""
    return statement.startswith("SELECT") and (
        "FROM users WHERE users.external_id = ? AND users.deleted_at IS NULL" in statement
    )


def _before_the_save_lookup(statement: str, _sent: list[str]) -> bool:
    """The first statement of ``ProfileRepository.save``: the owner's internal id."""
    return statement.startswith("SELECT users.id FROM users WHERE users.external_id = ?")


def _before_the_save_write(statement: str, _sent: list[str]) -> bool:
    return statement.startswith("UPDATE profiles")


def _before_the_next_write(statement: str, _sent: list[str]) -> bool:
    return statement.startswith(("UPDATE", "INSERT"))


def _right_after_the_account_lock(_statement: str, sent: list[str]) -> bool:
    return bool(sent) and sent[-1].startswith("UPDATE users")


# ─── the gate's reads vs a widening of the session's profile ─


_TV_UNLOCKED_TABLET_ON_KID = {_TV: ("Parent", True), _TABLET: ("Kid", False)}


def _widen_kid(home: _Household, to: int | None = None) -> Operation:
    return _put(home, _TV, "Kid", limit=to)


class TestTheGateNeverMixesASessionWithProfilesReadAfterAWidening:
    """S05b, M01-M05.

    The tablet is on Kid (12) with no unlock; the TV, unlocked, widens Kid,
    which also detaches the tablet. In either serial order the tablet acts
    under a limit (Kid's, or the lowest live one once detached), so each
    operation below needs an unlock it does not have. Held between its
    session read and its profiles read, the gate would pair "the tablet is
    on Kid" with "Kid is unrestricted".
    """

    @pytest.mark.parametrize(
        ("victim", "widened_to"),
        [
            pytest.param("switch-to-k14", None, id="S05b-gated-switch"),
            pytest.param("switch-to-parent", None, id="M01-switch-to-unrestricted"),
            pytest.param("switch-to-k14", 16, id="M02-switch-vs-widening-to-16"),
            pytest.param("create-unrestricted", None, id="M03-create"),
            pytest.param("delete-parent", None, id="M04-delete"),
            pytest.param("narrow-another", None, id="M05-update-another"),
        ],
    )
    async def test_the_operation_is_refused_as_in_every_serial_order(
        self, tmp_path: Path, victim: str, widened_to: int | None
    ) -> None:
        home = await _household(tmp_path, _STANDARD, _TV_UNLOCKED_TABLET_ON_KID)
        operation = {
            "switch-to-k14": _switch(home, _TABLET, "K14"),
            "switch-to-parent": _switch(home, _TABLET, "Parent"),
            "create-unrestricted": _create(home, _TABLET, "New", None),
            "delete-parent": _delete(home, _TABLET, "Parent"),
            "narrow-another": _put(home, _TABLET, "A", limit=8),
        }[victim]

        race = await _race(
            home, operation, _before_the_account_profiles_read, _widen_kid(home, widened_to)
        )

        rows = home.rows()
        assert not isinstance(race.attacker, Exception), race.attacker
        assert rows.profiles["Kid"] == (widened_to, True)
        assert isinstance(race.victim, ParentalPinRequiredError), race.victim
        assert rows.sessions[_TABLET] is None
        assert "New" not in rows.profiles
        assert rows.is_live("Parent")
        assert rows.profiles["A"] == (10, True)
        # The widening waited for the operation's account lock.
        assert race.attacker_meanwhile == "blocked"


# ─── a profile deleted under a write of its other fields ────


def _other_field_write(home: _Household, kind: str) -> Operation:
    return {
        "rename": _put(home, _TABLET, "Kid", name="Renamed"),
        "libraries": _put(home, _TABLET, "Kid", libraries=["lib_2xK9mPqR7nL4"]),
        "avatar-upload": _upload_avatar(home, "Kid"),
        "avatar-delete": _delete_avatar(home, "Kid"),
    }[kind]


# The profile routes take the account lock, so the delete waits for them; the
# avatar routes do not, so the delete lands first and they find no profile.
_SERIALISED_BY_THE_LOCK = {"rename", "libraries"}
_OTHER_FIELD_WRITES = sorted(["rename", "libraries", "avatar-upload", "avatar-delete"])


class TestAWriteOfOtherFieldsNeverRestoresADeletedProfile:
    """S08: the TV, unlocked, deletes Kid while the tablet writes another of its fields."""

    @pytest.mark.parametrize(
        "hold",
        [_before_the_save_lookup, _before_the_save_write],
        ids=["delete-before-the-lookup", "delete-before-the-update"],
    )
    @pytest.mark.parametrize("kind", _OTHER_FIELD_WRITES)
    async def test_the_delete_stands(self, tmp_path: Path, kind: str, hold: Hold) -> None:
        home = await _household(tmp_path, _STANDARD, _TV_UNLOCKED_TABLET_ON_KID, avatar_on="Kid")

        race = await _race(home, _other_field_write(home, kind), hold, _delete(home, _TV, "Kid"))

        assert race.attacker == "ok", race.attacker
        assert not home.rows().is_live("Kid")
        if kind in _SERIALISED_BY_THE_LOCK:
            assert not isinstance(race.victim, Exception), race.victim
            assert race.attacker_meanwhile == "blocked"
        else:
            assert isinstance(race.victim, ProfileNotFoundException), race.victim
            assert race.attacker_meanwhile == "finished"


class TestAWriteOfOtherFieldsNeverLeavesALimitWithoutAPin:
    """S08b: the TV deletes Kid (12), its only limited profile, then removes the PIN."""

    @pytest.mark.parametrize("kind", _OTHER_FIELD_WRITES)
    async def test_no_live_limit_outlives_the_pin(self, tmp_path: Path, kind: str) -> None:
        home = await _household(tmp_path, _SOLO, _TV_UNLOCKED_TABLET_ON_KID, avatar_on="Kid")

        race = await _race(
            home,
            _other_field_write(home, kind),
            _before_the_save_lookup,
            _in_order(_delete(home, _TV, "Kid"), _remove_pin(home)),
        )

        rows = home.rows()
        assert race.attacker == "ok", race.attacker
        assert (rows.pin, rows.live_limits()) == (None, {})
        assert not rows.is_live("Kid")
        if kind in _SERIALISED_BY_THE_LOCK:
            assert not isinstance(race.victim, Exception), race.victim
        else:
            assert isinstance(race.victim, ProfileNotFoundException), race.victim


# ─── the PIN read once, removed and set again (ABA) ─────────


async def _across_a_pin_aba(
    home: _Household, victim: Operation, first: Operation, second: Operation
) -> _Race:
    """Run ``first`` at the victim's account read and ``second`` at its next write.

    Each attack runs to its end, or until it waits for a lock the victim
    holds. ``second`` always starts after ``first`` has finished: when
    ``first`` is waiting for the victim, the victim is let go first. The
    result's attacker is ``first``.
    """
    timeline = _Timeline()
    held = _start(
        home,
        victim,
        name="victim",
        timeline=timeline,
        holds=(_before_the_account_read, _before_the_next_write),
    )
    assert await held.reached_hold(0)
    first_attack = _start(home, first, name="first", timeline=timeline)
    await first_attack.finished_or_blocked()
    held.release[0].set()
    reached_second = await held.reached_hold(1)

    meanwhile = await first_attack.finished_or_blocked()
    if meanwhile == "blocked":
        outcome = await held.finish()
        first_outcome = await first_attack.finish()
        await _start(home, second, name="second", timeline=timeline).finish()
        return _Race(victim=outcome, attacker=first_outcome, attacker_meanwhile=meanwhile)

    second_attack = _start(home, second, name="second", timeline=timeline)
    if reached_second:
        await second_attack.finished_or_blocked()
    outcome = await held.finish()
    await second_attack.finish()
    return _Race(victim=outcome, attacker=await first_attack.finish(), attacker_meanwhile=meanwhile)


class TestThePinTheGateReadIsThePinWhenTheChangeLands:
    """S14, S15: between the gate's account read and its write, the parent widens Kid
    and removes the PIN, then sets the PIN again and narrows Kid back to 12."""

    async def test_a_child_cannot_widen_its_own_profile_without_an_unlock(
        self, tmp_path: Path
    ) -> None:
        sessions = {_TV: ("Parent", True), _TABLET: ("Kid", False), _PHONE: ("Parent", False)}
        home = await _household(tmp_path, _SOLO, sessions)

        race = await _across_a_pin_aba(
            home,
            _put(home, _TABLET, "Kid", limit=None),
            _in_order(_widen_kid(home), _remove_pin(home)),
            _in_order(
                _set_pin(home), _put(home, _TV, "Kid", limit=12), _switch(home, _PHONE, "Kid")
            ),
        )

        rows = home.rows()
        assert isinstance(race.victim, ParentalPinRequiredError), race.victim
        assert race.attacker_meanwhile == "blocked"
        # Serially, the child first: refused; then the parent's changes, which
        # leave Kid limited again with the phone on it.
        assert (rows.profiles["Kid"], rows.sessions[_PHONE]) == ((12, True), "Kid")

    async def test_a_child_cannot_enter_an_unrestricted_profile_without_an_unlock(
        self, tmp_path: Path
    ) -> None:
        home = await _household(tmp_path, _SOLO, _TV_UNLOCKED_TABLET_ON_KID)

        race = await _across_a_pin_aba(
            home,
            _switch(home, _TABLET, "Free"),
            _in_order(_widen_kid(home), _remove_pin(home)),
            _in_order(_set_pin(home), _put(home, _TV, "Kid", limit=12)),
        )

        assert isinstance(race.victim, ParentalPinRequiredError), race.victim
        assert home.rows().sessions[_TABLET] != "Free"
        assert race.attacker_meanwhile == "blocked"


# ─── the account lock itself ───────────────────────────────


class TestTheAccountLock:
    async def test_a_widening_waits_for_a_gated_operation_holding_the_lock(
        self, tmp_path: Path
    ) -> None:
        # The tablet (Kid, 12) enters A (10), held right after its lock; the
        # TV's widening of Kid must wait inside its own lock statement, then
        # run after the switch commits — never between the switch's reads.
        home = await _household(tmp_path, _STANDARD, _TV_UNLOCKED_TABLET_ON_KID)
        timeline = _Timeline()
        switch = _start(
            home,
            _switch(home, _TABLET, "A"),
            name="switch",
            timeline=timeline,
            holds=(_right_after_the_account_lock,),
        )
        assert await switch.reached_hold(0)

        widening = _start(home, _widen_kid(home), name="widening", timeline=timeline)
        state = await widening.finished_or_blocked()
        waiting_in = widening.statements[-1] if widening.statements else ""

        switched = await switch.finish()
        widened = await widening.finish()

        assert state == "blocked"
        assert waiting_in.startswith("UPDATE users SET external_id=users.external_id")
        assert switched == "ok", switched
        assert getattr(widened, "maturity_limit", 0) is None, widened
        switch_commit = timeline.index("switch", lambda what: what == "COMMIT")
        widening_locked = timeline.index(
            "widening", lambda what: what.startswith("ran UPDATE users")
        )
        assert switch_commit < widening_locked
        rows = home.rows()
        # Serially, the switch first: the tablet enters A, which the widening
        # of Kid does not touch.
        assert (rows.sessions[_TABLET], rows.profiles["Kid"]) == ("A", (None, True))


# ─── the admin gate's snapshot ─────────────────────────────


class TestTheAdminGateReadsOneSnapshot:
    """C: the tablet (Kid, 12) asks for admin read authority while the TV widens Kid.

    A (10) stays limited, so the tablet's authority is suspended in both
    serial orders: on Kid before the widening, detached under the lowest
    live limit after it.
    """

    async def test_a_widening_never_grants_a_read_no_serial_order_grants(
        self, tmp_path: Path
    ) -> None:
        home = await _household(tmp_path, _STANDARD, _TV_UNLOCKED_TABLET_ON_KID)
        timeline = _Timeline()
        check = _start(
            home,
            _admin_read(home, _TABLET),
            name="check",
            timeline=timeline,
            holds=(_before_the_account_profiles_read,),
        )
        reached = await check.reached_hold(0)
        widening = _start(home, _widen_kid(home), name="widening", timeline=timeline)
        if reached:
            await widening.finished_or_blocked()

        access = await check.finish()
        widened = await widening.finish()

        assert getattr(widened, "maturity_limit", 0) is None, widened
        assert access is AdminAccessLevel.SUSPENDED, access
        # One statement leaves no boundary for a commit to land in.
        assert len(check.statements) == 1, check.statements
