"""In-memory fakes for identity use case unit tests.

Each repository fake mirrors the contract of its real counterpart but
keeps state in plain dicts/lists, so use-case tests stay independent
of SQLAlchemy and run fast.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

import pytest

from src.modules.identity.application.unit_of_work import (
    IdentityUnitOfWork,
    IdentityUnitOfWorkFactory,
)
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.repositories.access_token_repository import (
    AccessTokenRepository,
    AccessTokenSnapshot,
)
from src.modules.identity.domain.repositories.profile_repository import (
    ProfileRepository,
)
from src.modules.identity.domain.repositories.user_repository import UserRepository
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.profile_id import ProfileId
from src.modules.identity.domain.value_objects.user_id import UserId


class FakeUserRepository(UserRepository):
    """In-memory ``UserRepository`` keyed by external ID."""

    def __init__(self) -> None:
        self._items: dict[UserId, User] = {}

    async def save(self, user: User) -> User:
        if user.id is None:
            user = user.with_updates(id=UserId.generate())
        self._items[user.id] = user
        return user

    async def find_by_id(self, user_id: UserId) -> User | None:
        return self._items.get(user_id)

    async def find_by_email(self, email: Email) -> User | None:
        for u in self._items.values():
            if u.email == email:
                return u
        return None


class FakeProfileRepository(ProfileRepository):
    """In-memory ``ProfileRepository`` with soft-delete semantics."""

    def __init__(self) -> None:
        self._items: dict[ProfileId, Profile] = {}
        self._deleted: set[ProfileId] = set()

    async def save(self, profile: Profile) -> Profile:
        if profile.id is None:
            profile = profile.with_updates(id=ProfileId.generate())
        # ``with_updates`` bumps updated_at automatically (matches real repo).
        self._items[profile.id] = profile
        self._deleted.discard(profile.id)
        return profile

    async def find_by_id(self, profile_id: ProfileId) -> Profile | None:
        if profile_id in self._deleted:
            return None
        return self._items.get(profile_id)

    async def find_by_user(self, user_id: UserId) -> Sequence[Profile]:
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
    contract as the real SQLAlchemy implementation.
    """

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}

    def seed(
        self,
        *,
        token: str,
        user_id: UserId,
        current_profile_id: ProfileId | None = None,
        created_at: datetime | None = None,
    ) -> None:
        """Test helper: insert a session row directly (no use-case path)."""
        self._rows[token] = {
            "user_id": user_id,
            "current_profile_id": current_profile_id,
            "created_at": created_at or datetime.now(UTC),
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
    ) -> bool:
        row = self._rows.get(token)
        if row is None:
            return False
        row["current_profile_id"] = profile_id
        return True

    async def delete_older_than(self, cutoff: datetime) -> int:
        stale = [t for t, r in self._rows.items() if r["created_at"] < cutoff]
        for t in stale:
            del self._rows[t]
        return len(stale)


class FakeIdentityUnitOfWork(IdentityUnitOfWork):
    """In-memory UoW combining the three fake repositories."""

    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.profiles = FakeProfileRepository()
        self.access_tokens = FakeAccessTokenRepository()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
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


@pytest.fixture
def fake_uow() -> FakeIdentityUnitOfWork:
    """Fresh in-memory identity UoW per test."""
    return FakeIdentityUnitOfWork()


@pytest.fixture
def fake_uow_factory(fake_uow: FakeIdentityUnitOfWork) -> FakeIdentityUnitOfWorkFactory:
    """Factory yielding the test's UoW on every call."""
    return FakeIdentityUnitOfWorkFactory(fake_uow)
