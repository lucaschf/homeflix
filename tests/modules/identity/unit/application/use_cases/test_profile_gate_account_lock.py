"""Unit tests: the gated profile operations take the account lock first (ADR-035, Amendment 7).

The lock makes everything an operation reads afterwards one state that no
other parental change of the account can alter before it commits; a read made
before it would not be covered. What the lock does on a real database is pinned
in ``tests/modules/identity/integration/application/test_parental_gate_serialization.py``;
these tests pin that each use case takes it before any other repository call,
on an account with a PIN, where the gate reads the most.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    DeleteProfileInput,
    MaturityLimitChange,
    SwitchProfileInput,
    UpdateProfileInput,
)
from src.modules.identity.application.errors import UserNotFoundException
from src.modules.identity.application.use_cases.create_profile import CreateProfileUseCase
from src.modules.identity.application.use_cases.delete_profile import DeleteProfileUseCase
from src.modules.identity.application.use_cases.switch_profile import SwitchProfileUseCase
from src.modules.identity.application.use_cases.update_profile import UpdateProfileUseCase
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import (
    FakeAvatarStorage,
    FakeIdentityUnitOfWork,
    FakeIdentityUnitOfWorkFactory,
    record_repository_calls,
    seed_account,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
_TOKEN = "session-tablet"
_LOCK = "users.lock_for_parental_change"

Operation = Callable[
    [FakeIdentityUnitOfWorkFactory, UserId, dict[str, ProfileId]], Awaitable[object]
]


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


async def _switch(
    factory: FakeIdentityUnitOfWorkFactory, owner: UserId, profiles: dict[str, ProfileId]
) -> object:
    return await SwitchProfileUseCase(factory, clock=lambda: _NOW).execute(
        SwitchProfileInput(
            user_id=owner.value, target_profile_id=profiles["Parent"].value, session_token=_TOKEN
        )
    )


async def _widen(
    factory: FakeIdentityUnitOfWorkFactory, owner: UserId, profiles: dict[str, ProfileId]
) -> object:
    return await UpdateProfileUseCase(factory, clock=lambda: _NOW).execute(
        UpdateProfileInput(
            user_id=owner.value,
            profile_id=profiles["Kid"].value,
            maturity_limit=MaturityLimitChange(None),
            session_token=_TOKEN,
        )
    )


async def _create(
    factory: FakeIdentityUnitOfWorkFactory, owner: UserId, profiles: dict[str, ProfileId]
) -> object:
    return await CreateProfileUseCase(factory, clock=lambda: _NOW).execute(
        CreateProfileInput(user_id=owner.value, name="Free", session_token=_TOKEN)
    )


async def _delete(
    factory: FakeIdentityUnitOfWorkFactory, owner: UserId, profiles: dict[str, ProfileId]
) -> object:
    return await DeleteProfileUseCase(factory, FakeAvatarStorage(), clock=lambda: _NOW).execute(
        DeleteProfileInput(
            user_id=owner.value, profile_id=profiles["Parent"].value, session_token=_TOKEN
        )
    )


_OPERATIONS: dict[str, Operation] = {
    "switch": _switch,
    "update": _widen,
    "create": _create,
    "delete": _delete,
}


@pytest.fixture
async def household(
    fake_uow: FakeIdentityUnitOfWork, fake_uow_factory: FakeIdentityUnitOfWorkFactory
) -> tuple[UserId, dict[str, ProfileId]]:
    """An account with a PIN; the tablet is on Kid (12) with an open unlock."""
    owner = await seed_account(fake_uow_factory, parental_pin_hash="hashed::904518")
    profiles = {
        "Parent": await _profile(fake_uow, owner, "Parent", None),
        "Kid": await _profile(fake_uow, owner, "Kid", 12),
    }
    fake_uow.access_tokens.seed(
        token=_TOKEN,
        user_id=owner,
        current_profile_id=profiles["Kid"],
        unlock_until=_NOW + timedelta(minutes=5),
    )
    return owner, profiles


class TestTheAccountLockComesFirst:
    @pytest.mark.parametrize("operation", sorted(_OPERATIONS))
    async def test_before_any_other_repository_call(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        household: tuple[UserId, dict[str, ProfileId]],
        operation: str,
    ) -> None:
        owner, profiles = household
        calls = record_repository_calls(fake_uow)

        await _OPERATIONS[operation](fake_uow_factory, owner, profiles)

        assert calls[0] == _LOCK, calls
        assert calls.count(_LOCK) == 1, calls
        # The gate ran in full after it: its account read and its unlock spend.
        assert {"users.find_by_id", "access_tokens.consume_unlock"} <= set(calls[1:]), calls

    @pytest.mark.parametrize("operation", sorted(_OPERATIONS))
    async def test_an_account_gone_is_not_found_before_anything_is_read(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        household: tuple[UserId, dict[str, ProfileId]],
        operation: str,
    ) -> None:
        owner, profiles = household
        await fake_uow.users.soft_delete(owner)
        calls = record_repository_calls(fake_uow)

        with pytest.raises(UserNotFoundException):
            await _OPERATIONS[operation](fake_uow_factory, owner, profiles)

        assert calls == [_LOCK]
        assert fake_uow.rolled_back
