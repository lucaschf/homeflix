"""Unit tests for CreateProfileUseCase."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.modules.identity.application.dtos.identity_dtos import CreateProfileInput
from src.modules.identity.application.errors import UserNotFoundException
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.errors import (
    ParentalPinNotConfiguredError,
    ParentalPinRequiredError,
)
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import FakeIdentityUnitOfWork, FakeIdentityUnitOfWorkFactory, seed_account

_NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
_TOKEN = "session-abc"


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


def _use_case(factory: FakeIdentityUnitOfWorkFactory) -> CreateProfileUseCase:
    return CreateProfileUseCase(uow_factory=factory, clock=lambda: _NOW)


def _create(owner: UserId, limit: int | None, token: str | None = _TOKEN) -> CreateProfileInput:
    return CreateProfileInput(
        user_id=owner.value, name="New", maturity_limit=limit, session_token=token
    )


class TestCreateProfileUseCase:
    async def test_should_persist_profile_owned_by_caller(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        caller_id = await seed_account(fake_uow_factory)
        use_case = CreateProfileUseCase(uow_factory=fake_uow_factory)

        output = await use_case.execute(
            CreateProfileInput(
                user_id=caller_id.value,
                name="Lucas",
            )
        )

        assert output.id.startswith("prf_")
        assert output.user_id == caller_id.value
        assert output.name == "Lucas"
        assert output.maturity_limit is None
        assert output.is_kids is False
        assert output.avatar_url is None
        # Repository was actually written through:
        assert await fake_uow.profiles.count_for_user(caller_id) == 1

    async def test_should_assign_distinct_external_ids_to_multiple_profiles(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        caller_id = await seed_account(fake_uow_factory)
        use_case = CreateProfileUseCase(uow_factory=fake_uow_factory)

        a = await use_case.execute(CreateProfileInput(user_id=caller_id.value, name="Alice"))
        b = await use_case.execute(CreateProfileInput(user_id=caller_id.value, name="Bob"))

        assert a.id != b.id

    async def test_should_raise_when_the_account_is_unknown(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ):
        ghost = UserId.generate()

        with pytest.raises(UserNotFoundException):
            await _use_case(fake_uow_factory).execute(_create(ghost, None))

        assert await fake_uow.profiles.count_for_user(ghost) == 0


class TestCreateWithoutAPin:
    async def test_a_limit_is_not_configured_and_nothing_is_saved(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        owner = await seed_account(fake_uow_factory)

        with pytest.raises(ParentalPinNotConfiguredError):
            await _use_case(fake_uow_factory).execute(_create(owner, 12))

        assert await fake_uow.profiles.count_for_user(owner) == 0

    async def test_an_unrestricted_profile_passes_without_a_session(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
    ) -> None:
        # Operator scripts create an account's first profile outside a session.
        owner = await seed_account(fake_uow_factory)

        output = await _use_case(fake_uow_factory).execute(_create(owner, None, token=None))

        assert output.maturity_limit is None


class TestCreateParentalGate:
    """Amendment 7, decision 9: the ``POST`` row, on an account with a PIN."""

    @pytest.fixture
    async def owner(self, fake_uow_factory: FakeIdentityUnitOfWorkFactory) -> UserId:
        return await seed_account(fake_uow_factory, parental_pin_hash="hashed::904518")

    @pytest.mark.parametrize("limit", [None, 14])
    async def test_a_profile_above_a_limited_session_is_refused_and_not_saved(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
        limit: int | None,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=kid)

        with pytest.raises(ParentalPinRequiredError):
            await _use_case(fake_uow_factory).execute(_create(owner, limit))

        assert await fake_uow.profiles.count_for_user(owner) == 1

    @pytest.mark.parametrize("limit", [12, 10])
    async def test_a_profile_within_the_session_limit_needs_no_unlock(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
        limit: int,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=kid)

        output = await _use_case(fake_uow_factory).execute(_create(owner, limit))

        assert output.maturity_limit == limit

    @pytest.mark.parametrize("limit", [None, 16])
    async def test_an_unrestricted_session_creates_freely(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
        limit: int | None,
    ) -> None:
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=parent)

        output = await _use_case(fake_uow_factory).execute(_create(owner, limit))

        assert output.maturity_limit == limit

    async def test_an_unlock_pays_for_the_profile_and_is_spent(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        kid = await _profile(fake_uow, owner, "Kid", 12)
        fake_uow.access_tokens.seed(
            token=_TOKEN,
            user_id=owner,
            current_profile_id=kid,
            unlock_until=_NOW + timedelta(minutes=5),
        )
        use_case = _use_case(fake_uow_factory)

        await use_case.execute(_create(owner, None))
        with pytest.raises(ParentalPinRequiredError):
            await use_case.execute(_create(owner, None))

        assert await fake_uow.profiles.count_for_user(owner) == 2


class TestCreateRacingThePinRemoval:
    """Amendment 7 D2: the inserted limit is confirmed by the guarded limit write."""

    @pytest.fixture
    async def owner(
        self, fake_uow: FakeIdentityUnitOfWork, fake_uow_factory: FakeIdentityUnitOfWorkFactory
    ) -> UserId:
        """An account with a PIN whose session is on its unrestricted profile."""
        owner = await seed_account(fake_uow_factory, parental_pin_hash="hashed::904518")
        parent = await _profile(fake_uow, owner, "Parent", None)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=parent)
        return owner

    async def test_a_limit_is_confirmed_by_the_guarded_write_after_the_insert(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        calls: list[str] = []
        save, write = fake_uow.profiles.save, fake_uow.profiles.set_maturity_limit

        async def recording_save(profile: Profile) -> Profile:
            calls.append("insert")
            return await save(profile)

        async def recording_write(
            profile_id: ProfileId, *, expected: AgeRating | None, new: AgeRating | None
        ) -> bool:
            calls.append(f"guard {expected} -> {new}")
            return await write(profile_id, expected=expected, new=new)

        fake_uow.profiles.save = recording_save  # type: ignore[method-assign]
        fake_uow.profiles.set_maturity_limit = recording_write  # type: ignore[method-assign]

        output = await _use_case(fake_uow_factory).execute(_create(owner, 12))

        assert calls == ["insert", f"guard {AgeRating(12)} -> {AgeRating(12)}"]
        assert output.maturity_limit == 12

    async def test_a_pin_removed_before_the_insert_refuses_the_limit(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        # The gate read the PIN; it is gone by the time the profile is written.
        save = fake_uow.profiles.save

        async def pin_removed_meanwhile(profile: Profile) -> Profile:
            await fake_uow.users.set_parental_pin_hash(owner, None)
            return await save(profile)

        fake_uow.profiles.save = pin_removed_meanwhile  # type: ignore[method-assign]

        with pytest.raises(ParentalPinNotConfiguredError):
            await _use_case(fake_uow_factory).execute(_create(owner, 12))

    async def test_an_unrestricted_profile_needs_no_guard(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        owner: UserId,
    ) -> None:
        write = AsyncMock(wraps=fake_uow.profiles.set_maturity_limit)
        fake_uow.profiles.set_maturity_limit = write  # type: ignore[method-assign]

        await _use_case(fake_uow_factory).execute(_create(owner, None))

        write.assert_not_awaited()
