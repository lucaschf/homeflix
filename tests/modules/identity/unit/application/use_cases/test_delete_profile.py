"""Unit tests for DeleteProfileUseCase."""

from datetime import UTC, datetime, timedelta

import pytest

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    DeleteProfileInput,
)
from src.modules.identity.application.errors import (
    CannotDeleteLastProfileError,
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.delete_profile import (
    DeleteProfileUseCase,
)
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.errors import ParentalPinRequiredError
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import (
    FakeAvatarStorage,
    FakeIdentityUnitOfWork,
    FakeIdentityUnitOfWorkFactory,
    seed_account,
)

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


def _use_case(
    factory: FakeIdentityUnitOfWorkFactory, storage: FakeAvatarStorage
) -> DeleteProfileUseCase:
    return DeleteProfileUseCase(uow_factory=factory, avatar_storage=storage, clock=lambda: _NOW)


def _delete(owner: UserId, target: ProfileId) -> DeleteProfileInput:
    return DeleteProfileInput(user_id=owner.value, profile_id=target.value, session_token=_TOKEN)


class TestDeleteProfileUseCase:
    async def test_should_soft_delete_when_user_has_more_than_one_profile(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage,
    ):
        caller_id = await seed_account(fake_uow_factory)
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        keep = await creator.execute(CreateProfileInput(user_id=caller_id.value, name="Keep"))
        doomed = await creator.execute(CreateProfileInput(user_id=caller_id.value, name="Doomed"))

        use_case = DeleteProfileUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )
        await use_case.execute(
            DeleteProfileInput(
                user_id=caller_id.value,
                profile_id=doomed.id,
            )
        )

        # Deleted profile is gone, the other survives.
        assert await fake_uow.profiles.find_by_id(ProfileId(doomed.id)) is None
        assert await fake_uow.profiles.find_by_id(ProfileId(keep.id)) is not None
        assert await fake_uow.profiles.count_for_user(caller_id) == 1

    async def test_should_raise_when_deleting_last_profile(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory, fake_avatar_storage
    ):
        caller_id = await seed_account(fake_uow_factory)
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        only = await creator.execute(CreateProfileInput(user_id=caller_id.value, name="Only"))

        use_case = DeleteProfileUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )

        with pytest.raises(CannotDeleteLastProfileError):
            await use_case.execute(
                DeleteProfileInput(
                    user_id=caller_id.value,
                    profile_id=only.id,
                )
            )

    async def test_should_raise_when_profile_does_not_exist(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory, fake_avatar_storage
    ):
        use_case = DeleteProfileUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )

        caller_id = await seed_account(fake_uow_factory)

        with pytest.raises(ProfileNotFoundException):
            await use_case.execute(
                DeleteProfileInput(
                    user_id=caller_id.value,
                    profile_id=ProfileId.generate().value,
                )
            )

    async def test_should_raise_when_caller_is_not_the_owner(
        self, fake_uow_factory: FakeIdentityUnitOfWorkFactory, fake_avatar_storage
    ):
        owner_id = await seed_account(fake_uow_factory)
        intruder_id = await seed_account(fake_uow_factory)
        creator = CreateProfileUseCase(uow_factory=fake_uow_factory)
        # Owner has 2 profiles so the last-profile guard wouldn't kick in.
        await creator.execute(CreateProfileInput(user_id=owner_id.value, name="Other"))
        target = await creator.execute(CreateProfileInput(user_id=owner_id.value, name="Target"))

        use_case = DeleteProfileUseCase(
            uow_factory=fake_uow_factory, avatar_storage=fake_avatar_storage
        )

        with pytest.raises(ProfileOwnershipViolation):
            await use_case.execute(
                DeleteProfileInput(
                    user_id=intruder_id.value,
                    profile_id=target.id,
                )
            )


class TestDeleteParentalGate:
    """Amendment 8: on an account with a PIN, every deletion needs an unlock."""

    @pytest.fixture
    async def owner(self, fake_uow_factory: FakeIdentityUnitOfWorkFactory) -> UserId:
        return await seed_account(fake_uow_factory, parental_pin_hash="hashed::904518")

    @pytest.mark.parametrize(
        ("session", "target"),
        [
            pytest.param(None, None, id="unrestricted-session-unrestricted-target"),
            pytest.param(None, 12, id="unrestricted-session-limited-target"),
            pytest.param(12, None, id="limited-session-unrestricted-target"),
            pytest.param(12, 10, id="limited-session-limited-target"),
        ],
    )
    async def test_any_deletion_without_an_unlock_is_refused_and_the_profile_stays_alive(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
        owner: UserId,
        session: int | None,
        target: int | None,
    ) -> None:
        active = await _profile(fake_uow, owner, "Active", session)
        doomed = await _profile(fake_uow, owner, "Doomed", target)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=active)

        with pytest.raises(ParentalPinRequiredError):
            await _use_case(fake_uow_factory, fake_avatar_storage).execute(_delete(owner, doomed))

        assert await fake_uow.profiles.find_by_id(doomed) is not None
        assert fake_avatar_storage.deleted == []

    async def test_an_unlock_pays_for_one_deletion_and_is_spent(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
        owner: UserId,
    ) -> None:
        parent = await _profile(fake_uow, owner, "Parent", None)
        guest = await _profile(fake_uow, owner, "Guest", None)
        other_guest = await _profile(fake_uow, owner, "Other guest", None)
        fake_uow.access_tokens.seed(
            token=_TOKEN,
            user_id=owner,
            current_profile_id=parent,
            unlock_until=_NOW + timedelta(minutes=5),
        )
        use_case = _use_case(fake_uow_factory, fake_avatar_storage)

        await use_case.execute(_delete(owner, guest))
        with pytest.raises(ParentalPinRequiredError):
            await use_case.execute(_delete(owner, other_guest))

        assert await fake_uow.profiles.find_by_id(guest) is None
        assert await fake_uow.profiles.find_by_id(other_guest) is not None
        assert fake_avatar_storage.deleted == [guest.value]

    async def test_not_found_answers_before_the_gate(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
        owner: UserId,
    ) -> None:
        parent = await _profile(fake_uow, owner, "Parent", None)
        await _profile(fake_uow, owner, "Guest", None)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=parent)

        with pytest.raises(ProfileNotFoundException):
            await _use_case(fake_uow_factory, fake_avatar_storage).execute(
                _delete(owner, ProfileId.generate())
            )

    @pytest.mark.parametrize("limit", [None, 12], ids=["unrestricted", "limited"])
    async def test_the_last_profile_guard_answers_before_the_gate(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
        owner: UserId,
        limit: int | None,
    ) -> None:
        only = await _profile(fake_uow, owner, "Only", limit)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=only)

        with pytest.raises(CannotDeleteLastProfileError):
            await _use_case(fake_uow_factory, fake_avatar_storage).execute(_delete(owner, only))

    async def test_ownership_answers_before_the_gate(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_avatar_storage: FakeAvatarStorage,
        owner: UserId,
    ) -> None:
        parent = await _profile(fake_uow, owner, "Parent", None)
        stranger = await seed_account(fake_uow_factory)
        await _profile(fake_uow, stranger, "Stranger", None)
        strangers_guest = await _profile(fake_uow, stranger, "Stranger guest", None)
        fake_uow.access_tokens.seed(token=_TOKEN, user_id=owner, current_profile_id=parent)

        with pytest.raises(ProfileOwnershipViolation):
            await _use_case(fake_uow_factory, fake_avatar_storage).execute(
                _delete(owner, strangers_guest)
            )
