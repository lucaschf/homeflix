"""Unit tests for GetAdminAccessUseCase and EnsureAdminAuthorityUseCase (ADR-035).

The use cases apply the Amendment 7 admin matrix to what the session and the
account's live profiles say. The matrix itself is pinned in
``tests/modules/identity/unit/domain/services/test_parental_gate.py``; these
tests pin what the use cases feed it, what they read and what they raise.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ForbiddenOperationException
from src.modules.identity.application.dtos.identity_dtos import (
    AdminAccessLevel,
    GetAdminAccessInput,
)
from src.modules.identity.application.errors import NoActiveSessionError
from src.modules.identity.application.use_cases.ensure_admin_authority import (
    EnsureAdminAuthorityUseCase,
)
from src.modules.identity.application.use_cases.get_admin_access import (
    GetAdminAccessUseCase,
)
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.errors import ParentalPinRequiredError
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
_TOKEN = "device-token"
_OWNER = UserId.generate()


async def _profile(fake_uow: FakeIdentityUnitOfWork, name: str, limit: int | None) -> Profile:
    profile = Profile(
        user_id=_OWNER,
        name=ProfileName(name),
        maturity_limit=None if limit is None else AgeRating(limit),
    )
    saved = await fake_uow.profiles.save(profile)
    assert saved.id is not None
    return saved


def _input(
    *,
    role: UserRole = UserRole.ADMIN,
    pin: bool = True,
    is_write: bool = False,
    token: str = _TOKEN,
) -> GetAdminAccessInput:
    return GetAdminAccessInput(
        user_id=str(_OWNER),
        role=role,
        parental_pin_configured=pin,
        session_token=token,
        is_write=is_write,
    )


def _use_case(factory: FakeIdentityUnitOfWorkFactory) -> GetAdminAccessUseCase:
    return GetAdminAccessUseCase(uow_factory=factory, clock=lambda: _NOW)


def _spy_reads(fake_uow: FakeIdentityUnitOfWork) -> tuple[AsyncMock, AsyncMock]:
    """Count the two reads the decision is allowed to make."""
    state = AsyncMock(wraps=fake_uow.access_tokens.get_parental_state)
    profiles = AsyncMock(wraps=fake_uow.profiles.find_by_user)
    fake_uow.access_tokens.get_parental_state = state  # type: ignore[method-assign]
    fake_uow.profiles.find_by_user = profiles  # type: ignore[method-assign]
    return state, profiles


class TestWithoutTheGate:
    @pytest.mark.parametrize("pin", [True, False])
    async def test_member_has_no_admin_access_and_reads_nothing(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        pin: bool,
    ) -> None:
        state, profiles = _spy_reads(fake_uow)

        access = await _use_case(fake_uow_factory).execute(_input(role=UserRole.MEMBER, pin=pin))

        assert access is AdminAccessLevel.NONE
        state.assert_not_awaited()
        profiles.assert_not_awaited()

    @pytest.mark.parametrize("is_write", [False, True])
    async def test_admin_without_pin_is_granted_and_reads_nothing(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        is_write: bool,
    ) -> None:
        # Even a limited profile on the session: with no PIN the gate is inert.
        kid = await _profile(fake_uow, "Kid", 10)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=_OWNER, current_profile_id=kid.id)
        state, profiles = _spy_reads(fake_uow)

        access = await _use_case(fake_uow_factory).execute(_input(pin=False, is_write=is_write))

        assert access is AdminAccessLevel.GRANTED
        state.assert_not_awaited()
        profiles.assert_not_awaited()


class TestWithAPin:
    async def test_reads_the_session_and_the_live_profiles_once_each(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        parent = await _profile(fake_uow, "Parent", None)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=_OWNER, current_profile_id=parent.id)
        state, profiles = _spy_reads(fake_uow)

        access = await _use_case(fake_uow_factory).execute(_input())

        assert access is AdminAccessLevel.GRANTED
        state.assert_awaited_once_with(_TOKEN)
        profiles.assert_awaited_once_with(_OWNER)

    @pytest.mark.parametrize(
        ("active", "read", "write"),
        [
            pytest.param("parent", "granted", "suspended", id="unrestricted-with-limited-sibling"),
            pytest.param("kid", "suspended", "suspended", id="limited"),
            pytest.param("deleted", "suspended", "suspended", id="deleted-profile"),
            pytest.param("none", "suspended", "suspended", id="no-profile"),
        ],
    )
    async def test_follows_the_matrix_for_the_session_profile(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        active: str,
        read: str,
        write: str,
    ) -> None:
        parent = await _profile(fake_uow, "Parent", None)
        kid = await _profile(fake_uow, "Kid", 12)
        gone = await _profile(fake_uow, "Gone", None)
        await fake_uow.profiles.delete(gone.id)  # type: ignore[arg-type]
        selected = {"parent": parent.id, "kid": kid.id, "deleted": gone.id, "none": None}[active]
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=_OWNER, current_profile_id=selected)
        use_case = _use_case(fake_uow_factory)

        assert await use_case.execute(_input(is_write=False)) == AdminAccessLevel(read)
        assert await use_case.execute(_input(is_write=True)) == AdminAccessLevel(write)

    async def test_deleted_profile_is_suspended_even_when_no_live_profile_is_limited(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        # Treating the stale id as "no profile selected" would grant here (D1).
        await _profile(fake_uow, "Parent", None)
        gone = await _profile(fake_uow, "Gone", None)
        await fake_uow.profiles.delete(gone.id)  # type: ignore[arg-type]
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=_OWNER, current_profile_id=gone.id)

        access = await _use_case(fake_uow_factory).execute(_input())

        assert access is AdminAccessLevel.SUSPENDED

    @pytest.mark.parametrize(
        ("unlock_until", "expected"),
        [
            pytest.param(_NOW + timedelta(seconds=1), "granted", id="open"),
            pytest.param(_NOW, "suspended", id="ends-now"),
            pytest.param(_NOW - timedelta(seconds=1), "suspended", id="passed"),
        ],
    )
    @pytest.mark.parametrize("is_write", [False, True])
    async def test_an_open_unlock_grants_and_is_not_spent(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        unlock_until: datetime,
        expected: str,
        is_write: bool,
    ) -> None:
        kid = await _profile(fake_uow, "Kid", 12)
        fake_uow.access_tokens.seed(
            token=_TOKEN, user_id=_OWNER, current_profile_id=kid.id, unlock_until=unlock_until
        )
        use_case = _use_case(fake_uow_factory)

        first = await use_case.execute(_input(is_write=is_write))
        second = await use_case.execute(_input(is_write=is_write))

        assert (first, second) == (AdminAccessLevel(expected), AdminAccessLevel(expected))
        state = await fake_uow.access_tokens.get_parental_state(_TOKEN)
        assert state is not None and state.unlock_until == unlock_until

    @pytest.mark.parametrize("token", ["unknown-token", "other-account-token"])
    async def test_a_token_without_a_session_of_the_account_is_suspended(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        token: str,
    ) -> None:
        # Nothing proves the profile or the unlock of such a session.
        await _profile(fake_uow, "Parent", None)
        fake_uow.access_tokens.seed(
            token="other-account-token",
            user_id=UserId.generate(),
            unlock_until=_NOW + timedelta(minutes=5),
        )

        access = await _use_case(fake_uow_factory).execute(_input(token=token))

        assert access is AdminAccessLevel.SUSPENDED


class TestEnsureAdminAuthority:
    @staticmethod
    def _ensure(access: AdminAccessLevel) -> tuple[EnsureAdminAuthorityUseCase, AsyncMock]:
        get_admin_access = AsyncMock(spec=GetAdminAccessUseCase)
        get_admin_access.execute.return_value = access
        return EnsureAdminAuthorityUseCase(get_admin_access=get_admin_access), get_admin_access

    async def test_granted_passes_with_the_same_input(self) -> None:
        ensure, get_admin_access = self._ensure(AdminAccessLevel.GRANTED)
        sent = _input(is_write=True)

        await ensure.execute(sent)

        get_admin_access.execute.assert_awaited_once_with(sent)

    async def test_suspended_is_pin_required_never_401(self) -> None:
        ensure, _ = self._ensure(AdminAccessLevel.SUSPENDED)

        with pytest.raises(ParentalPinRequiredError) as exc_info:
            await ensure.execute(_input())

        assert exc_info.value.code == "PARENTAL_PIN_REQUIRED"
        assert not isinstance(exc_info.value, NoActiveSessionError)

    async def test_no_admin_role_is_admin_required(self) -> None:
        ensure, _ = self._ensure(AdminAccessLevel.NONE)

        with pytest.raises(ForbiddenOperationException) as exc_info:
            await ensure.execute(_input(role=UserRole.MEMBER))

        assert exc_info.value.message_code == "ADMIN_REQUIRED"

    async def test_decides_from_the_real_use_case(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        parent = await _profile(fake_uow, "Parent", None)
        await _profile(fake_uow, "Kid", 12)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=_OWNER, current_profile_id=parent.id)
        ensure = EnsureAdminAuthorityUseCase(get_admin_access=_use_case(fake_uow_factory))

        await ensure.execute(_input(is_write=False))
        with pytest.raises(ParentalPinRequiredError):
            await ensure.execute(_input(is_write=True))
