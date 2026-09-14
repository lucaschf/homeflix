"""Integration tests: parental PIN writes racing account changes (ADR-035).

Setting or removing the PIN verifies the account password (and, to set it,
hashes the PIN) between reading the user and writing the hash. Those calls
are slow and synchronous, so another request can commit in that window.
These tests commit a role demotion or a soft delete exactly there — from
inside the hasher — through a second, independent Unit of Work on its own
connection, then check that the PIN write neither reverts that change nor
lands on a deleted account.

The database is a SQLite file configured like the app (``Database``, with
foreign keys on): racing transactions need connections of their own, which
the shared in-memory fixture cannot give.
"""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest
from sqlalchemy import select

from src.building_blocks.infrastructure.in_process_event_bus import InProcessEventBus
from src.infrastructure.persistence import Base
from src.infrastructure.persistence.database import Database
from src.modules.identity.application.dtos.identity_dtos import (
    DeleteAdminUserInput,
    RemoveParentalPinInput,
    SetParentalPinInput,
    UpdateUserRoleInput,
)
from src.modules.identity.application.errors import UserNotFoundException
from src.modules.identity.application.ports import PasswordHasherPort
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases.delete_admin_user import (
    DeleteAdminUserUseCase,
)
from src.modules.identity.application.use_cases.remove_parental_pin import (
    RemoveParentalPinUseCase,
)
from src.modules.identity.application.use_cases.set_parental_pin import (
    SetParentalPinUseCase,
)
from src.modules.identity.application.use_cases.update_user_role import (
    UpdateUserRoleUseCase,
)
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyIdentityUnitOfWorkFactory,
)

pytestmark = pytest.mark.integration

_PASSWORD = "correct-horse"
_PIN = "904518"
_EXISTING_PIN_HASH = "hashed::111111"

ConcurrentChange = Callable[[IdentityUnitOfWorkFactory], Awaitable[None]]
Window = Literal["verify", "hash"]


class _CommitsInsideTheHasher(PasswordHasherPort):
    """Deterministic hasher that lets another transaction commit mid-call.

    The first call to the method named by ``window`` runs ``commit_elsewhere``
    before answering, so whatever it commits lands after the use case read
    the user and before it writes the PIN hash.
    """

    def __init__(self, commit_elsewhere: Callable[[], None], window: Window) -> None:
        self._commit_elsewhere = commit_elsewhere
        self._window = window
        self.fired = False

    def _enter(self, method: Window) -> None:
        if method == self._window and not self.fired:
            self.fired = True
            self._commit_elsewhere()

    def hash(self, password: str) -> str:
        self._enter("hash")
        return f"hashed::{password}"

    def verify(self, plain: str, hashed: str) -> bool:
        self._enter("verify")
        return hashed == f"hashed::{plain}"


@dataclass(frozen=True)
class _StoredRow:
    role: str
    is_deleted: bool
    parental_pin_hash: str | None


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
async def file_uow_factory(database_url: str) -> AsyncGenerator[IdentityUnitOfWorkFactory, None]:
    """Identity Unit of Work factory on the SQLite file, for the use case under test."""
    database = Database(database_url)
    await database.connect()
    yield SqlAlchemyIdentityUnitOfWorkFactory(database.session_factory)
    await database.disconnect()


def _commit_elsewhere(database_url: str, change: ConcurrentChange) -> Callable[[], None]:
    """Build a callback that commits ``change`` through an independent Unit of Work.

    The hasher port is synchronous and runs on the test's event loop, so it
    cannot await. The change runs on a separate thread instead, with its own
    event loop, engine and connection, and the callback blocks until it has
    committed — much like a request served by another worker.
    """

    async def run() -> None:
        database = Database(database_url)
        await database.connect()
        try:
            await change(SqlAlchemyIdentityUnitOfWorkFactory(database.session_factory))
        finally:
            await database.disconnect()

    def commit() -> None:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, run()).result()

    return commit


def _demote(user: User, acting_admin: User) -> ConcurrentChange:
    async def change(uow_factory: IdentityUnitOfWorkFactory) -> None:
        await UpdateUserRoleUseCase(uow_factory).execute(
            UpdateUserRoleInput(
                user_id=str(user.id), role=UserRole.MEMBER, acting_admin_id=str(acting_admin.id)
            ),
        )

    return change


def _soft_delete(user: User, acting_admin: User) -> ConcurrentChange:
    async def change(uow_factory: IdentityUnitOfWorkFactory) -> None:
        await DeleteAdminUserUseCase(uow_factory, InProcessEventBus()).execute(
            DeleteAdminUserInput(user_id=str(user.id), acting_admin_id=str(acting_admin.id)),
        )

    return change


async def _seed_admins(
    uow_factory: IdentityUnitOfWorkFactory, *, parental_pin_hash: str | None = None
) -> tuple[User, User]:
    """Seed the account under test and a second admin acting on it.

    Both are admins so demoting the account never trips the last-admin guard.
    """
    async with uow_factory() as uow:
        account = await uow.users.save(
            User(
                email=Email("parent@example.com"),
                role=UserRole.ADMIN,
                hashed_password=f"hashed::{_PASSWORD}",
                parental_pin_hash=parental_pin_hash,
            )
        )
        other_admin = await uow.users.save(
            User(email=Email("other-admin@example.com"), role=UserRole.ADMIN, hashed_password="hp")
        )
    return account, other_admin


async def _stored_row(database_url: str, user: User) -> _StoredRow:
    """Read the user's row directly: ``find_by_id`` hides soft-deleted users."""
    database = Database(database_url)
    await database.connect()
    try:
        async with database.session_factory() as session:
            row = (
                await session.execute(
                    select(UserModel.role, UserModel.deleted_at, UserModel.parental_pin_hash).where(
                        UserModel.external_id == str(user.id)
                    )
                )
            ).one()
    finally:
        await database.disconnect()
    return _StoredRow(
        role=row.role,
        is_deleted=row.deleted_at is not None,
        parental_pin_hash=row.parental_pin_hash,
    )


class TestSetParentalPinRacingAccountChanges:
    @pytest.mark.parametrize("window", ["verify", "hash"])
    async def test_a_demotion_committed_meanwhile_should_survive_and_the_pin_be_stored(
        self,
        database_url: str,
        file_uow_factory: IdentityUnitOfWorkFactory,
        window: Window,
    ) -> None:
        account, other_admin = await _seed_admins(file_uow_factory)
        hasher = _CommitsInsideTheHasher(
            _commit_elsewhere(database_url, _demote(account, other_admin)), window
        )

        await SetParentalPinUseCase(file_uow_factory, hasher).execute(
            SetParentalPinInput(user_id=str(account.id), current_password=_PASSWORD, pin=_PIN),
        )

        assert hasher.fired is True
        assert await _stored_row(database_url, account) == _StoredRow(
            role=UserRole.MEMBER.value, is_deleted=False, parental_pin_hash=f"hashed::{_PIN}"
        )

    @pytest.mark.parametrize("window", ["verify", "hash"])
    async def test_a_soft_delete_committed_meanwhile_should_survive_and_answer_not_found(
        self,
        database_url: str,
        file_uow_factory: IdentityUnitOfWorkFactory,
        window: Window,
    ) -> None:
        account, other_admin = await _seed_admins(file_uow_factory)
        hasher = _CommitsInsideTheHasher(
            _commit_elsewhere(database_url, _soft_delete(account, other_admin)), window
        )

        with pytest.raises(UserNotFoundException) as exc_info:
            await SetParentalPinUseCase(file_uow_factory, hasher).execute(
                SetParentalPinInput(user_id=str(account.id), current_password=_PASSWORD, pin=_PIN),
            )

        assert hasher.fired is True
        assert exc_info.value.code == "USER_NOT_FOUND"
        assert await _stored_row(database_url, account) == _StoredRow(
            role=UserRole.ADMIN.value, is_deleted=True, parental_pin_hash=None
        )


class TestRemoveParentalPinRacingAccountChanges:
    async def test_a_demotion_committed_meanwhile_should_survive_and_the_pin_be_cleared(
        self,
        database_url: str,
        file_uow_factory: IdentityUnitOfWorkFactory,
    ) -> None:
        account, other_admin = await _seed_admins(
            file_uow_factory, parental_pin_hash=_EXISTING_PIN_HASH
        )
        hasher = _CommitsInsideTheHasher(
            _commit_elsewhere(database_url, _demote(account, other_admin)), "verify"
        )

        await RemoveParentalPinUseCase(file_uow_factory, hasher).execute(
            RemoveParentalPinInput(user_id=str(account.id), current_password=_PASSWORD),
        )

        assert hasher.fired is True
        assert await _stored_row(database_url, account) == _StoredRow(
            role=UserRole.MEMBER.value, is_deleted=False, parental_pin_hash=None
        )

    async def test_a_soft_delete_committed_meanwhile_should_survive_and_answer_not_found(
        self,
        database_url: str,
        file_uow_factory: IdentityUnitOfWorkFactory,
    ) -> None:
        account, other_admin = await _seed_admins(
            file_uow_factory, parental_pin_hash=_EXISTING_PIN_HASH
        )
        hasher = _CommitsInsideTheHasher(
            _commit_elsewhere(database_url, _soft_delete(account, other_admin)), "verify"
        )

        with pytest.raises(UserNotFoundException) as exc_info:
            await RemoveParentalPinUseCase(file_uow_factory, hasher).execute(
                RemoveParentalPinInput(user_id=str(account.id), current_password=_PASSWORD),
            )

        assert hasher.fired is True
        assert exc_info.value.code == "USER_NOT_FOUND"
        assert await _stored_row(database_url, account) == _StoredRow(
            role=UserRole.ADMIN.value, is_deleted=True, parental_pin_hash=_EXISTING_PIN_HASH
        )
