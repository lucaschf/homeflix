"""In-memory fakes for identity use case unit tests.

Each repository fake mirrors the contract of its real counterpart but
keeps state in plain dicts/lists, so use-case tests stay independent
of SQLAlchemy and run fast.
"""

import inspect
import secrets
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self

import pytest

from src.modules.identity.application.ports import AvatarStoragePort, PasswordHasherPort
from src.modules.identity.application.unit_of_work import (
    IdentityUnitOfWork,
    IdentityUnitOfWorkFactory,
)
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.repositories.access_token_repository import (
    AccessTokenRepository,
    AccessTokenSnapshot,
    ParentalSessionSnapshot,
    ParentalSessionState,
    PinAttemptReservation,
)
from src.modules.identity.domain.repositories.profile_repository import (
    ProfileRepository,
)
from src.modules.identity.domain.repositories.user_repository import UserRepository
from src.modules.identity.domain.services.parental_gate import LockoutPolicy
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


def _limit_value(limit: AgeRating | None) -> int | None:
    return None if limit is None else limit.value


class FakeUserRepository(UserRepository):
    """In-memory ``UserRepository`` keyed by external ID.

    ``profiles`` is the Unit of Work's profile fake, which the PIN removal
    checks for limits like the real statement's subquery.
    """

    def __init__(self) -> None:
        self._items: dict[UserId, User] = {}
        self._deleted: set[UserId] = set()
        self.profiles: FakeProfileRepository | None = None

    async def save(self, user: User) -> User:
        if user.id is None:
            user = user.with_updates(id=UserId.generate())
        elif user.id in self._items:
            # Like the real repository, an update never writes the PIN hash.
            user = user.with_updates(
                parental_pin_hash=self._items[user.id].parental_pin_hash,
                updated_at=user.updated_at,
            )
        self._items[user.id] = user
        self._deleted.discard(user.id)
        return user

    async def set_parental_pin_hash(self, user_id: UserId, hashed: str | None) -> bool:
        if user_id not in self._items or user_id in self._deleted:
            return False
        self._items[user_id] = self._items[user_id].with_updates(parental_pin_hash=hashed)
        return True

    async def clear_unused_parental_pin_hash(self, user_id: UserId) -> bool:
        if user_id not in self._items or user_id in self._deleted:
            return False
        if self.profiles is not None and any(
            p.maturity_limit is not None for p in await self.profiles.find_by_user(user_id)
        ):
            return False
        self._items[user_id] = self._items[user_id].with_updates(parental_pin_hash=None)
        return True

    async def lock_for_parental_change(self, user_id: UserId) -> bool:
        # One test runs one request at a time: there is nothing to wait for,
        # only the answer for a missing or deleted account.
        return user_id in self._items and user_id not in self._deleted

    async def find_by_id(self, user_id: UserId) -> User | None:
        if user_id in self._deleted:
            return None
        return self._items.get(user_id)

    async def find_by_email(self, email: Email) -> User | None:
        for uid, u in self._items.items():
            if uid in self._deleted:
                continue
            if u.email == email:
                return u
        return None

    async def list_paginated(
        self,
        *,
        role: UserRole | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[User]:
        active = [u for uid, u in self._items.items() if uid not in self._deleted]
        if role is not None:
            active = [u for u in active if u.role == role]
        active.sort(key=lambda u: u.created_at, reverse=True)
        return active[offset : offset + limit]

    async def count(self, *, role: UserRole | None = None) -> int:
        active = [u for uid, u in self._items.items() if uid not in self._deleted]
        if role is not None:
            active = [u for u in active if u.role == role]
        return len(active)

    async def count_active_admins(self) -> int:
        return sum(
            1
            for uid, u in self._items.items()
            if uid not in self._deleted and u.is_active and u.role == UserRole.ADMIN
        )

    async def soft_delete(self, user_id: UserId) -> bool:
        if user_id not in self._items or user_id in self._deleted:
            return False
        self._deleted.add(user_id)
        return True


class FakeProfileRepository(ProfileRepository):
    """In-memory ``ProfileRepository`` with soft-delete semantics.

    ``users`` is the Unit of Work's user fake, which the limit write checks
    for a PIN like the real statement's subquery.
    """

    def __init__(self, users: FakeUserRepository | None = None) -> None:
        self._items: dict[ProfileId, Profile] = {}
        self._deleted: set[ProfileId] = set()
        self._users = users

    async def save(self, profile: Profile) -> Profile | None:
        if profile.id is None:
            profile = profile.with_updates(id=ProfileId.generate())
        elif profile.id in self._deleted:
            # Like the real repository, a deleted profile is never restored.
            return None
        elif profile.id in self._items:
            # Like the real repository, an update never writes the limit.
            profile = profile.with_updates(
                maturity_limit=self._items[profile.id].maturity_limit,
                updated_at=profile.updated_at,
            )
        # ``with_updates`` bumps updated_at automatically (matches real repo).
        self._items[profile.id] = profile
        return profile

    async def set_maturity_limit(
        self,
        profile_id: ProfileId,
        *,
        expected: AgeRating | None,
        new: AgeRating | None,
    ) -> bool:
        current = await self.find_by_id(profile_id)
        if current is None or _limit_value(current.maturity_limit) != _limit_value(expected):
            return False
        if new is not None:
            owner = None if self._users is None else self._users._items.get(current.user_id)
            if owner is None or not owner.has_parental_pin:
                return False
        self._items[profile_id] = current.with_maturity_limit(new)
        return True

    async def find_by_id(self, profile_id: ProfileId) -> Profile | None:
        if profile_id in self._deleted:
            return None
        return self._items.get(profile_id)

    async def find_by_user(self, user_id: UserId) -> Sequence[Profile]:
        return self._live_for(user_id)

    def _live_for(self, user_id: UserId) -> list[Profile]:
        active = [
            p for p in self._items.values() if p.user_id == user_id and p.id not in self._deleted
        ]
        return sorted(active, key=lambda p: p.name.value)

    async def count_for_user(self, user_id: UserId) -> int:
        return sum(
            1 for p in self._items.values() if p.user_id == user_id and p.id not in self._deleted
        )

    async def delete(self, profile_id: ProfileId) -> bool:
        if profile_id not in self._items or profile_id in self._deleted:
            return False
        self._deleted.add(profile_id)
        return True


class FakeAccessTokenRepository(AccessTokenRepository):
    """In-memory ``AccessTokenRepository``.

    Stored as a small list of dicts keyed by token; reads return
    ``AccessTokenSnapshot`` instances so the use case sees the same
    contract as the real SQLAlchemy implementation. ``profiles`` is the
    Unit of Work's profile fake, which the switch compare-and-set reads.
    """

    def __init__(self, profiles: FakeProfileRepository | None = None) -> None:
        self._rows: dict[str, dict] = {}
        self._profiles = profiles

    def seed(
        self,
        *,
        token: str,
        user_id: UserId,
        current_profile_id: ProfileId | None = None,
        created_at: datetime | None = None,
        unlock_until: datetime | None = None,
    ) -> None:
        """Test helper: insert a session row directly (no use-case path)."""
        self._rows[token] = {
            "user_id": user_id,
            "current_profile_id": current_profile_id,
            "created_at": created_at or datetime.now(UTC),
            "failed_attempts": 0,
            "lockouts": 0,
            "locked_until": None,
            "unlock_until": unlock_until,
        }

    async def get_by_token(self, token: str) -> AccessTokenSnapshot | None:
        row = self._rows.get(token)
        if row is None:
            return None
        return AccessTokenSnapshot(
            token=token,
            user_id=row["user_id"],
            current_profile_id=row["current_profile_id"],
            created_at=row["created_at"],
        )

    async def update_current_profile(
        self,
        token: str,
        profile_id: ProfileId | None,
        *,
        expected_limit: AgeRating | None,
    ) -> bool:
        if profile_id is not None and self._profiles is not None:
            if profile_id not in self._profiles._items:
                raise ValueError(f"Profile {profile_id} does not exist")
            target = await self._profiles.find_by_id(profile_id)
            if target is None or _limit_value(target.maturity_limit) != _limit_value(
                expected_limit
            ):
                return False
        row = self._rows.get(token)
        if row is None:
            return False
        row["current_profile_id"] = profile_id
        row["unlock_until"] = None
        return True

    async def delete_older_than(self, cutoff: datetime) -> int:
        stale = [t for t, r in self._rows.items() if r["created_at"] < cutoff]
        for t in stale:
            del self._rows[t]
        return len(stale)

    async def get_parental_state(self, token: str) -> ParentalSessionState | None:
        return self._parental_state(token)

    def _parental_state(self, token: str) -> ParentalSessionState | None:
        row = self._rows.get(token)
        if row is None:
            return None
        return ParentalSessionState(
            user_id=row["user_id"],
            current_profile_id=row["current_profile_id"],
            failed_attempts=row["failed_attempts"],
            lockouts=row["lockouts"],
            locked_until=row["locked_until"],
            unlock_until=row["unlock_until"],
        )

    async def get_parental_snapshot(self, token: str) -> ParentalSessionSnapshot | None:
        # Built without the public reads, so a test recording them sees one call.
        state = self._parental_state(token)
        if state is None:
            return None
        profiles = [] if self._profiles is None else self._profiles._live_for(state.user_id)
        return ParentalSessionSnapshot(state=state, account_profiles=profiles)

    async def reserve_pin_attempt(
        self,
        token: str,
        *,
        now: datetime,
        policy: LockoutPolicy,
    ) -> PinAttemptReservation:
        # The same rules as the real single UPDATE, applied to the dict.
        row = self._rows.get(token)
        if row is None:
            return PinAttemptReservation(granted=False, failed_attempts=0, locked_until=None)
        locked_until = row["locked_until"]
        if locked_until is not None and locked_until > now:
            return PinAttemptReservation(
                granted=False,
                failed_attempts=row["failed_attempts"],
                locked_until=locked_until,
            )
        attempts, lockouts = row["failed_attempts"], row["lockouts"]
        if locked_until is not None and attempts >= policy.max_attempts:
            attempts = 0
        if locked_until is not None and locked_until + policy.decay <= now:
            lockouts = 0
        attempts += 1
        started = None
        if attempts >= policy.max_attempts:
            started = now + policy.lock_duration(lockouts)
            lockouts += 1
            row["locked_until"] = started
        row["failed_attempts"], row["lockouts"] = attempts, lockouts
        return PinAttemptReservation(granted=True, failed_attempts=attempts, locked_until=started)

    async def record_pin_success(
        self,
        token: str,
        *,
        now: datetime,
        unlock_until: datetime,
    ) -> None:
        row = self._rows.get(token)
        if row is None:
            return
        row["failed_attempts"] = 0
        row["unlock_until"] = unlock_until
        if row["locked_until"] is not None and row["locked_until"] > now:
            row["locked_until"] = now

    async def consume_unlock(self, token: str, *, now: datetime) -> bool:
        row = self._rows.get(token)
        if row is None or row["unlock_until"] is None or row["unlock_until"] <= now:
            return False
        row["unlock_until"] = None
        return True

    async def clear_unlock(self, token: str) -> None:
        row = self._rows.get(token)
        if row is not None:
            row["unlock_until"] = None

    async def detach_profile_sessions(self, profile_id: ProfileId, *, except_token: str) -> int:
        detached = 0
        for token, row in self._rows.items():
            if token != except_token and row["current_profile_id"] == profile_id:
                row["current_profile_id"] = None
                row["unlock_until"] = None
                detached += 1
        return detached


class FakeIdentityUnitOfWork(IdentityUnitOfWork):
    """In-memory UoW combining the three fake repositories.

    ``active`` is ``True`` only inside ``async with``, so a test can tell
    whether a call happened inside a transaction.
    """

    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.profiles = FakeProfileRepository(users=self.users)
        self.users.profiles = self.profiles
        self.access_tokens = FakeAccessTokenRepository(profiles=self.profiles)
        self.committed = False
        self.rolled_back = False
        self.active = False

    async def __aenter__(self) -> Self:
        self.active = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.active = False
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeIdentityUnitOfWorkFactory(IdentityUnitOfWorkFactory):
    """Returns the same ``FakeIdentityUnitOfWork`` instance on every call.

    Use case tests typically execute one ``async with`` block per call
    to ``execute()``; sharing the UoW across calls keeps the in-memory
    state live across multiple invocations within one test.
    """

    def __init__(self, uow: FakeIdentityUnitOfWork) -> None:
        self._uow = uow

    def __call__(self) -> IdentityUnitOfWork:
        return self._uow


async def seed_account(
    uow_factory: FakeIdentityUnitOfWorkFactory,
    *,
    parental_pin_hash: str | None = None,
) -> UserId:
    """Test helper: save an account, so the profile use cases can read their caller.

    Every profile operation reads the caller's account for its parental PIN
    (ADR-035) and refuses an unknown one.
    """
    uow = uow_factory()
    user = await uow.users.save(
        User(
            email=Email(f"account-{secrets.token_hex(6)}@example.com"),
            hashed_password="hp",
            parental_pin_hash=parental_pin_hash,
        )
    )
    assert user.id is not None
    return user.id


def record_repository_calls(uow: FakeIdentityUnitOfWork) -> list[str]:
    """Test helper: list, in order, every repository method awaited from now on.

    Entries read ``"users.find_by_id"``; a fake calling another fake records
    that call too. Lets a test pin what a use case does first.
    """
    calls: list[str] = []

    def recording(name: str, method: Callable[..., Awaitable[Any]]) -> Callable[..., Any]:
        async def record(*args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            return await method(*args, **kwargs)

        return record

    for prefix, repository in (
        ("users", uow.users),
        ("profiles", uow.profiles),
        ("access_tokens", uow.access_tokens),
    ):
        for attribute in dir(repository):
            method = getattr(repository, attribute)
            if not attribute.startswith("_") and inspect.iscoroutinefunction(method):
                setattr(repository, attribute, recording(f"{prefix}.{attribute}", method))
    return calls


class FakePasswordHasher(PasswordHasherPort):
    """Deterministic ``PasswordHasherPort`` that records every verification.

    ``hash`` is a reversible tag (``hashed::<plain>``) so tests can tell a
    stored hash from the plaintext it came from; ``verify_calls`` lets a
    test prove a verification never happened.
    """

    def __init__(self) -> None:
        self.verify_calls: list[str] = []

    def hash(self, password: str) -> str:
        return f"hashed::{password}"

    def verify(self, plain: str, hashed: str) -> bool:
        self.verify_calls.append(hashed)
        # Not ``self.hash(plain)``: a test recording ``hash`` calls must see
        # only the use case's own.
        return hashed == f"hashed::{plain}"


class FakeAvatarStorage(AvatarStoragePort):
    """In-memory ``AvatarStoragePort`` recording save / delete calls.

    Tests that exercise the avatar use cases inspect ``saved`` /
    ``deleted`` to verify the use case wired the port correctly.
    Tests that just need a stand-in (e.g. ``DeleteProfileUseCase``
    cascade) don't need to inspect anything — the empty default
    behaviour is enough.
    """

    def __init__(self) -> None:
        self.saved: list[tuple[str, bytes, str]] = []
        self.deleted: list[str] = []

    async def save(
        self,
        profile_id: str,
        *,
        content: bytes,
        declared_mime_type: str,
    ) -> str:
        self.saved.append((profile_id, content, declared_mime_type))
        return f"/api/v1/profiles/{profile_id}/avatar?v=fake"

    async def delete(self, profile_id: str) -> None:
        self.deleted.append(profile_id)


@pytest.fixture
def fake_uow() -> FakeIdentityUnitOfWork:
    """Fresh in-memory identity UoW per test."""
    return FakeIdentityUnitOfWork()


@pytest.fixture
def fake_uow_factory(fake_uow: FakeIdentityUnitOfWork) -> FakeIdentityUnitOfWorkFactory:
    """Factory yielding the test's UoW on every call."""
    return FakeIdentityUnitOfWorkFactory(fake_uow)


@pytest.fixture
def fake_avatar_storage() -> FakeAvatarStorage:
    """Fresh in-memory ``AvatarStoragePort`` per test."""
    return FakeAvatarStorage()


@pytest.fixture
def fake_password_hasher() -> FakePasswordHasher:
    """Fresh recording ``PasswordHasherPort`` per test."""
    return FakePasswordHasher()
