"""Unit tests for UpdateProfileUseCase."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.building_blocks.domain.errors import DomainConflictException
from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    MaturityLimitChange,
    UpdateProfileInput,
)
from src.modules.identity.application.errors import (
    ProfileNotFoundException,
    ProfileOwnershipViolation,
    UserNotFoundException,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.update_profile import (
    UpdateProfileUseCase,
)
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.errors import (
    ParentalPinNotConfiguredError,
    ParentalPinRequiredError,
)
from src.modules.identity.domain.repositories.access_token_repository import (
    ParentalSessionState,
)
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory, seed_account

_NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
_TV = "token-tv"
_TABLET = "token-tablet"
_LIBRARY = "lib_movies123456"


async def _profile(
    fake_uow: FakeIdentityUnitOfWork,
    owner: UserId,
    name: str,
    limit: int | None,
    libraries: list[str] | None = None,
) -> ProfileId:
    saved = await fake_uow.profiles.save(
        Profile(
            user_id=owner,
            name=ProfileName(name),
            maturity_limit=None if limit is None else AgeRating(limit),
            allowed_library_ids=libraries or [],
        )
    )
    assert saved.id is not None
    return saved.id


async def _limit(fake_uow: FakeIdentityUnitOfWork, profile_id: ProfileId) -> int | None:
    stored = await fake_uow.profiles.find_by_id(profile_id)
    assert stored is not None
    return None if stored.maturity_limit is None else stored.maturity_limit.value


async def _state(fake_uow: FakeIdentityUnitOfWork, token: str) -> ParentalSessionState:
    state = await fake_uow.access_tokens.get_parental_state(token)
    assert state is not None
    return state


def _use_case(factory: FakeIdentityUnitOfWorkFactory) -> UpdateProfileUseCase:
    return UpdateProfileUseCase(uow_factory=factory, clock=lambda: _NOW)


def _set_limit(
    owner: UserId, target: ProfileId, limit: int | None, token: str = _TV
) -> UpdateProfileInput:
    return UpdateProfileInput(
        user_id=owner.value,
        profile_id=target.value,
        maturity_limit=MaturityLimitChange(limit),
        session_token=token,
    )


class TestUpdateProfileUseCase:
    async def test_should_update_only_supplied_fields(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ):
        caller_id = await seed_account(fake_uow_factory)
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        original = await creator.execute(
            CreateProfileInput(
                user_id=caller_id.value,
                name="Lucas",
                avatar_url="https://x/old.png",
            )
        )

        use_case = UpdateProfileUseCase(uow_factory=fake_uow_factory)
        output = await use_case.execute(
            UpdateProfileInput(
                user_id=caller_id.value,
                profile_id=original.id,
                name="Luc",  # only name supplied
            )
        )

        assert output.id == original.id
        assert output.name == "Luc"  # changed
        assert output.avatar_url == "https://x/old.png"  # unchanged
        assert output.maturity_limit is None  # unchanged

    async def test_should_keep_the_maturity_limit_on_a_partial_update(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        caller_id = await seed_account(fake_uow_factory, parental_pin_hash="hashed::904518")
        limited = await fake_uow.profiles.save(
            Profile.create(user_id=caller_id, name=ProfileName("Kids")).with_maturity_limit(
                AgeRating(12)
            )
        )
        assert limited.id is not None

        use_case = UpdateProfileUseCase(uow_factory=fake_uow_factory)
        output = await use_case.execute(
            UpdateProfileInput(
                user_id=caller_id.value,
                profile_id=limited.id.value,
                name="Renamed",
                allowed_library_ids=["lib_movies123456"],
            )
        )

        assert output.name == "Renamed"
        assert output.maturity_limit == 12
        assert output.is_kids is True

    async def test_should_raise_when_profile_does_not_exist(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ):
        use_case = UpdateProfileUseCase(uow_factory=fake_uow_factory)
        caller_id = await seed_account(fake_uow_factory)

        with pytest.raises(ProfileNotFoundException):
            await use_case.execute(
                UpdateProfileInput(
                    user_id=caller_id.value,
                    profile_id=ProfileId.generate().value,
                    name="Whatever",
                )
            )

    async def test_a_profile_deleted_before_the_save_is_not_found_and_stays_deleted(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # ADR-035: the save never restores it, so the rename answers 404.
        owner_id = await seed_account(fake_uow_factory)
        target = await _profile(fake_uow, owner_id, "Kid", None)
        await _profile(fake_uow, owner_id, "Parent", None)
        save = fake_uow.profiles.save

        async def deleted_first(profile: Profile) -> Profile | None:
            await fake_uow.profiles.delete(target)
            return await save(profile)

        monkeypatch.setattr(fake_uow.profiles, "save", deleted_first)

        with pytest.raises(ProfileNotFoundException):
            await UpdateProfileUseCase(uow_factory=fake_uow_factory).execute(
                UpdateProfileInput(user_id=owner_id.value, profile_id=target.value, name="Renamed")
            )

        assert await fake_uow.profiles.find_by_id(target) is None

    async def test_should_raise_when_caller_is_not_the_owner(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ):
        owner_id = await seed_account(fake_uow_factory)
        intruder_id = await seed_account(fake_uow_factory)
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        target = await creator.execute(
            CreateProfileInput(user_id=owner_id.value, name="OwnersProfile")
        )

        use_case = UpdateProfileUseCase(uow_factory=fake_uow_factory)

        with pytest.raises(ProfileOwnershipViolation):
            await use_case.execute(
                UpdateProfileInput(
                    user_id=intruder_id.value,
                    profile_id=target.id,
                    name="Hijacked",
                )
            )


class TestMaturityLimitWithoutAPin:
    """Amendment 7 D2: no limit may be written on an account without a PIN."""

    async def test_setting_a_limit_is_not_configured_and_writes_nothing(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        owner = await seed_account(fake_uow_factory)
        target = await _profile(fake_uow, owner, "Kid", None)

        with pytest.raises(ParentalPinNotConfiguredError) as exc_info:
            await _use_case(fake_uow_factory).execute(_set_limit(owner, target, 12))

        assert exc_info.value.code == "PARENTAL_PIN_NOT_CONFIGURED"
        assert await _limit(fake_uow, target) is None

    async def test_sending_no_limit_passes(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        owner = await seed_account(fake_uow_factory)
        target = await _profile(fake_uow, owner, "Kid", None)

        output = await _use_case(fake_uow_factory).execute(_set_limit(owner, target, None))

        assert output.maturity_limit is None


class TestUpdateParentalGate:
    """Amendment 7, decision 9: the ``PUT`` row, on an account with a PIN."""

    @pytest.fixture
    async def owner(self, fake_uow_factory: FakeIdentityUnitOfWorkFactory) -> UserId:
        return await seed_account(fake_uow_factory, parental_pin_hash="hashed::904518")

    def _unlock(self, fake_uow: FakeIdentityUnitOfWork, token: str = _TV) -> None:
        row = fake_uow.access_tokens._rows[token]
        row["unlock_until"] = _NOW + timedelta(minutes=5)

    async def test_a_rename_with_the_same_libraries_passes_without_an_unlock(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        # The web client sends name and libraries on every submit, and no limit.
        kid = await _profile(fake_uow, owner, "Kid", 12, [_LIBRARY])
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=kid)

        output = await _use_case(fake_uow_factory).execute(
            UpdateProfileInput(
                user_id=owner.value,
                profile_id=kid.value,
                name="Renamed",
                allowed_library_ids=[_LIBRARY],
                session_token=_TV,
            )
        )

        assert (output.name, output.maturity_limit) == ("Renamed", 12)

    async def test_sending_the_same_limit_needs_no_unlock(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        # Presence of the field is not a change: only the resulting limit counts.
        kid = await _profile(fake_uow, owner, "Kid", 12)
        other = await _profile(fake_uow, owner, "Other", 12)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=kid)

        output = await _use_case(fake_uow_factory).execute(_set_limit(owner, other, 12))

        assert output.maturity_limit == 12

    async def test_a_wider_library_list_with_the_same_limit_needs_no_unlock(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        # Amendment 7 D5: the ACL is not gated.
        kid = await _profile(fake_uow, owner, "Kid", 12, [_LIBRARY])
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=kid)

        output = await _use_case(fake_uow_factory).execute(
            UpdateProfileInput(
                user_id=owner.value,
                profile_id=kid.value,
                allowed_library_ids=[_LIBRARY, "lib_series123456"],
                session_token=_TV,
            )
        )

        assert output.allowed_library_ids == [_LIBRARY, "lib_series123456"]

    @pytest.mark.parametrize("wider", [14, None])
    @pytest.mark.parametrize("on", ["kid", "parent"])
    async def test_widening_is_refused_from_any_session_before_any_write(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
        wider: int | None,
        on: str,
    ) -> None:
        # The fake keeps writes made before a raise, so a save or a detach
        # ahead of the gate would show here.
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(
            token=_TV, user_id=owner, current_profile_id=kid if on == "kid" else parent
        )
        fake_uow.access_tokens.seed(token=_TABLET, user_id=owner, current_profile_id=kid)

        with pytest.raises(ParentalPinRequiredError):
            await _use_case(fake_uow_factory).execute(_set_limit(owner, kid, wider))

        assert await _limit(fake_uow, kid) == 12
        assert (await _state(fake_uow, _TABLET)).current_profile_id == kid

    @pytest.mark.parametrize("wider", [14, None])
    async def test_widening_with_an_unlock_spends_it_and_detaches_the_other_sessions(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
        wider: int | None,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=kid)
        fake_uow.access_tokens.seed(
            token=_TABLET,
            user_id=owner,
            current_profile_id=kid,
            unlock_until=_NOW + timedelta(minutes=3),
        )
        fake_uow.access_tokens.seed(token="token-phone", user_id=owner, current_profile_id=parent)
        self._unlock(fake_uow)

        output = await _use_case(fake_uow_factory).execute(_set_limit(owner, kid, wider))

        assert output.maturity_limit == wider
        tv = await _state(fake_uow, _TV)
        tablet = await _state(fake_uow, _TABLET)
        phone = await _state(fake_uow, "token-phone")
        assert (tv.current_profile_id, tv.unlock_until) == (kid, None)
        assert (tablet.current_profile_id, tablet.unlock_until) == (None, None)
        assert phone.current_profile_id == parent

    async def test_one_unlock_pays_for_one_widening(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        a = await _profile(fake_uow, owner, "A", 10)
        b = await _profile(fake_uow, owner, "B", 10)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=parent)
        self._unlock(fake_uow)
        use_case = _use_case(fake_uow_factory)

        await use_case.execute(_set_limit(owner, a, 14))
        with pytest.raises(ParentalPinRequiredError):
            await use_case.execute(_set_limit(owner, b, 14))

        assert (await _limit(fake_uow, a), await _limit(fake_uow, b)) == (14, 10)

    async def test_narrowing_the_active_profile_needs_no_unlock(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        fourteen = await _profile(fake_uow, owner, "Teen", 14)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=fourteen)

        output = await _use_case(fake_uow_factory).execute(_set_limit(owner, fourteen, 12))

        assert output.maturity_limit == 12

    async def test_narrowing_another_profile_needs_an_unlock_from_a_limited_session(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 10)
        fourteen = await _profile(fake_uow, owner, "Teen", 14)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=kid)

        with pytest.raises(ParentalPinRequiredError):
            await _use_case(fake_uow_factory).execute(_set_limit(owner, fourteen, 12))

        assert await _limit(fake_uow, fourteen) == 14

    async def test_narrowing_another_profile_from_an_unrestricted_session_passes(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        parent = await _profile(fake_uow, owner, "Parent", None)
        fourteen = await _profile(fake_uow, owner, "Teen", 14)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=parent)

        output = await _use_case(fake_uow_factory).execute(_set_limit(owner, fourteen, 12))

        assert output.maturity_limit == 12

    async def test_an_omitted_limit_is_left_alone_and_a_null_one_removes_it(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        parent = await _profile(fake_uow, owner, "Parent", None)
        kid = await _profile(fake_uow, owner, "Kid", 12)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=parent)
        use_case = _use_case(fake_uow_factory)

        omitted = await use_case.execute(
            UpdateProfileInput(
                user_id=owner.value, profile_id=kid.value, name="Kid", session_token=_TV
            )
        )
        self._unlock(fake_uow)
        removed = await use_case.execute(_set_limit(owner, kid, None))

        assert (omitted.maturity_limit, removed.maturity_limit) == (12, None)


class TestUpdateRacingALimitChange:
    """The limit is written by one compare-and-set, never by ``save``."""

    @pytest.fixture
    async def owner(self, fake_uow_factory: FakeIdentityUnitOfWorkFactory) -> UserId:
        return await seed_account(fake_uow_factory, parental_pin_hash="hashed::904518")

    def _before_limit_write(
        self, fake_uow: FakeIdentityUnitOfWork, change: Callable[[], Awaitable[object]]
    ) -> AsyncMock:
        write = fake_uow.profiles.set_maturity_limit

        async def racing(
            profile_id: ProfileId, *, expected: AgeRating | None, new: AgeRating | None
        ) -> bool:
            await change()
            return await write(profile_id, expected=expected, new=new)

        spy = AsyncMock(side_effect=racing)
        fake_uow.profiles.set_maturity_limit = spy  # type: ignore[method-assign]
        return spy

    async def test_a_rename_leaves_a_limit_changed_after_the_read_and_writes_no_limit(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=parent)
        write = AsyncMock(wraps=fake_uow.profiles.set_maturity_limit)
        save = fake_uow.profiles.save

        async def narrowed_meanwhile(profile: Profile) -> Profile:
            assert profile.id is not None
            await write(profile.id, expected=AgeRating(12), new=AgeRating(10))
            return await save(profile)

        fake_uow.profiles.set_maturity_limit = write  # type: ignore[method-assign]
        fake_uow.profiles.save = narrowed_meanwhile  # type: ignore[method-assign]

        output = await _use_case(fake_uow_factory).execute(
            UpdateProfileInput(
                user_id=owner.value, profile_id=kid.value, name="Renamed", session_token=_TV
            )
        )

        write.assert_awaited_once()  # only the concurrent narrowing
        assert (output.name, output.maturity_limit) == ("Renamed", 10)
        assert await _limit(fake_uow, kid) == 10

    async def test_a_limit_changed_since_the_gate_is_a_conflict_that_detaches_nobody(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=parent)
        fake_uow.access_tokens.seed(token=_TABLET, user_id=owner, current_profile_id=kid)
        fake_uow.access_tokens._rows[_TV]["unlock_until"] = _NOW + timedelta(minutes=5)
        write = fake_uow.profiles.set_maturity_limit
        self._before_limit_write(
            fake_uow, lambda: write(kid, expected=AgeRating(12), new=AgeRating(10))
        )

        with pytest.raises(DomainConflictException) as exc_info:
            await _use_case(fake_uow_factory).execute(_set_limit(owner, kid, None))

        assert exc_info.value.code == "DOMAIN_CONFLICT"
        assert await _limit(fake_uow, kid) == 10
        assert (await _state(fake_uow, _TABLET)).current_profile_id == kid

    async def test_a_pin_removed_since_the_gate_is_not_configured(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", None)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=parent)
        self._before_limit_write(
            fake_uow, lambda: fake_uow.users.set_parental_pin_hash(owner, None)
        )

        with pytest.raises(ParentalPinNotConfiguredError):
            await _use_case(fake_uow_factory).execute(_set_limit(owner, kid, 12))

        assert await _limit(fake_uow, kid) is None

    async def test_a_profile_deleted_since_the_gate_is_not_found(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=parent)
        self._before_limit_write(fake_uow, lambda: fake_uow.profiles.delete(kid))

        with pytest.raises(ProfileNotFoundException):
            await _use_case(fake_uow_factory).execute(_set_limit(owner, kid, 10))

    async def test_an_account_deleted_since_the_gate_is_not_found(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=parent)
        write = fake_uow.profiles.set_maturity_limit

        async def deleted_and_narrowed() -> None:
            await write(kid, expected=AgeRating(12), new=AgeRating(8))
            await fake_uow.users.soft_delete(owner)

        self._before_limit_write(fake_uow, deleted_and_narrowed)

        with pytest.raises(UserNotFoundException):
            await _use_case(fake_uow_factory).execute(_set_limit(owner, kid, 10))

    async def test_an_unchanged_limit_is_not_written(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        fake_uow.access_tokens.seed(token=_TV, user_id=owner, current_profile_id=kid)
        spy = self._before_limit_write(fake_uow, AsyncMock())

        await _use_case(fake_uow_factory).execute(_set_limit(owner, kid, 12))

        spy.assert_not_awaited()
