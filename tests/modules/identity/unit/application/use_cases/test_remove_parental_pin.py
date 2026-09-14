"""Unit tests for RemoveParentalPinUseCase (ADR-035, Amendment 7 D3)."""

from unittest.mock import AsyncMock

import pytest

from src.modules.identity.application.dtos.identity_dtos import RemoveParentalPinInput
from src.modules.identity.application.errors import (
    AccountPasswordInvalidError,
    UserNotFoundException,
)
from src.modules.identity.application.use_cases.remove_parental_pin import (
    RemoveParentalPinUseCase,
)
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.shared_kernel.value_objects.user_id import UserId

from .conftest import (
    FakeIdentityUnitOfWork,
    FakeIdentityUnitOfWorkFactory,
    FakePasswordHasher,
)

pytestmark = pytest.mark.unit

_PASSWORD = "correct-horse"


async def _seed(
    fake_uow: FakeIdentityUnitOfWork,
    hasher: FakePasswordHasher,
    *,
    with_pin: bool = True,
) -> User:
    user = User(
        email=Email("parent@example.com"),
        hashed_password=hasher.hash(_PASSWORD),
        parental_pin_hash=hasher.hash("904518") if with_pin else None,
    )
    async with fake_uow:
        return await fake_uow.users.save(user)


async def _stored(fake_uow: FakeIdentityUnitOfWork, user: User) -> User:
    assert user.id is not None
    async with fake_uow:
        stored = await fake_uow.users.find_by_id(user.id)
    assert stored is not None
    return stored


def _use_case(
    factory: FakeIdentityUnitOfWorkFactory, hasher: FakePasswordHasher
) -> RemoveParentalPinUseCase:
    return RemoveParentalPinUseCase(uow_factory=factory, password_hasher=hasher)


class TestRemoveParentalPin:
    async def test_should_clear_the_pin(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)

        await _use_case(fake_uow_factory, fake_password_hasher).execute(
            RemoveParentalPinInput(user_id=str(user.id), current_password=_PASSWORD),
        )

        stored = await _stored(fake_uow, user)
        assert stored.has_parental_pin is False
        assert stored.parental_pin_hash is None

    async def test_should_succeed_when_no_pin_is_configured(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher, with_pin=False)

        await _use_case(fake_uow_factory, fake_password_hasher).execute(
            RemoveParentalPinInput(user_id=str(user.id), current_password=_PASSWORD),
        )

        assert (await _stored(fake_uow, user)).has_parental_pin is False

    async def test_wrong_password_should_be_refused_without_writing(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)
        write = AsyncMock(wraps=fake_uow.users.set_parental_pin_hash)
        save = AsyncMock(wraps=fake_uow.users.save)
        monkeypatch.setattr(fake_uow.users, "set_parental_pin_hash", write)
        monkeypatch.setattr(fake_uow.users, "save", save)

        with pytest.raises(AccountPasswordInvalidError):
            await _use_case(fake_uow_factory, fake_password_hasher).execute(
                RemoveParentalPinInput(user_id=str(user.id), current_password="wrong"),
            )

        write.assert_not_awaited()
        save.assert_not_awaited()
        assert (await _stored(fake_uow, user)).has_parental_pin is True

    async def test_password_check_should_run_between_the_read_and_the_write(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Saving the entity read before the (slow) password check writes back
        # a stale user, undoing a concurrent demotion or soft delete. Each
        # call records whether a Unit of Work was open when it ran.
        user = await _seed(fake_uow, fake_password_hasher)
        calls: list[tuple[str, bool]] = []
        users, hasher = fake_uow.users, fake_password_hasher
        find_by_id, write, verify = users.find_by_id, users.set_parental_pin_hash, hasher.verify

        async def recording_find_by_id(user_id: UserId) -> User | None:
            calls.append(("read", fake_uow.active))
            return await find_by_id(user_id)

        async def recording_write(user_id: UserId, hashed: str | None) -> bool:
            calls.append(("write", fake_uow.active))
            return await write(user_id, hashed)

        def recording_verify(plain: str, hashed: str) -> bool:
            calls.append(("verify", fake_uow.active))
            return verify(plain, hashed)

        monkeypatch.setattr(users, "find_by_id", recording_find_by_id)
        monkeypatch.setattr(users, "set_parental_pin_hash", recording_write)
        monkeypatch.setattr(hasher, "verify", recording_verify)
        save = AsyncMock(wraps=users.save)
        monkeypatch.setattr(users, "save", save)

        await _use_case(fake_uow_factory, hasher).execute(
            RemoveParentalPinInput(user_id=str(user.id), current_password=_PASSWORD),
        )

        assert calls == [("read", True), ("verify", False), ("write", True)]
        save.assert_not_awaited()

    async def test_user_gone_at_the_narrow_write_should_raise_not_found(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Deleted while the password was being checked: the delete wins.
        user = await _seed(fake_uow, fake_password_hasher)
        monkeypatch.setattr(fake_uow.users, "set_parental_pin_hash", AsyncMock(return_value=False))

        with pytest.raises(UserNotFoundException) as exc_info:
            await _use_case(fake_uow_factory, fake_password_hasher).execute(
                RemoveParentalPinInput(user_id=str(user.id), current_password=_PASSWORD),
            )

        assert exc_info.value.code == "USER_NOT_FOUND"

    async def test_unknown_user_should_raise_not_found(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        with pytest.raises(UserNotFoundException):
            await _use_case(fake_uow_factory, fake_password_hasher).execute(
                RemoveParentalPinInput(user_id=str(UserId.generate()), current_password=_PASSWORD),
            )

    def test_input_repr_should_not_contain_the_password(self) -> None:
        input_dto = RemoveParentalPinInput(user_id="usr_abcdefghijkl", current_password=_PASSWORD)

        assert _PASSWORD not in repr(input_dto)
