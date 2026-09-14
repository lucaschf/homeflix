"""Unit tests for SetParentalPinUseCase (ADR-035, Amendment 7 D3/D4)."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import (
    ForbiddenOperationException,
    UnauthorizedOperationException,
)
from src.building_blocks.domain.errors import DomainValidationException
from src.modules.identity.application.dtos.identity_dtos import SetParentalPinInput
from src.modules.identity.application.errors import (
    AccountPasswordInvalidError,
    UserNotFoundException,
)
from src.modules.identity.application.use_cases.set_parental_pin import (
    SetParentalPinUseCase,
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
_PIN = "904518"


async def _seed(
    fake_uow: FakeIdentityUnitOfWork,
    hasher: FakePasswordHasher,
    *,
    pin_hash: str | None = None,
) -> User:
    user = User(
        email=Email("parent@example.com"),
        hashed_password=hasher.hash(_PASSWORD),
        parental_pin_hash=pin_hash,
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
) -> SetParentalPinUseCase:
    return SetParentalPinUseCase(uow_factory=factory, password_hasher=hasher)


class TestSetParentalPin:
    async def test_should_store_the_hash_of_the_pin(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)

        await _use_case(fake_uow_factory, fake_password_hasher).execute(
            SetParentalPinInput(user_id=str(user.id), current_password=_PASSWORD, pin=_PIN),
        )

        stored = await _stored(fake_uow, user)
        assert stored.has_parental_pin is True
        assert stored.parental_pin_hash == fake_password_hasher.hash(_PIN)
        assert stored.parental_pin_hash != _PIN

    async def test_should_replace_an_existing_pin(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = await _seed(
            fake_uow, fake_password_hasher, pin_hash=fake_password_hasher.hash("111111")
        )

        await _use_case(fake_uow_factory, fake_password_hasher).execute(
            SetParentalPinInput(user_id=str(user.id), current_password=_PASSWORD, pin=_PIN),
        )

        stored = await _stored(fake_uow, user)
        assert stored.parental_pin_hash == fake_password_hasher.hash(_PIN)


class TestSetParentalPinTransactions:
    async def test_password_check_and_hashing_should_run_between_the_read_and_the_write(
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
        find_by_id, write = users.find_by_id, users.set_parental_pin_hash
        verify, hash_ = hasher.verify, hasher.hash

        async def recording_find_by_id(user_id: UserId) -> User | None:
            calls.append(("read", fake_uow.active))
            return await find_by_id(user_id)

        async def recording_write(user_id: UserId, hashed: str | None) -> bool:
            calls.append(("write", fake_uow.active))
            return await write(user_id, hashed)

        def recording_verify(plain: str, hashed: str) -> bool:
            calls.append(("verify", fake_uow.active))
            return verify(plain, hashed)

        def recording_hash(password: str) -> str:
            calls.append(("hash", fake_uow.active))
            return hash_(password)

        monkeypatch.setattr(users, "find_by_id", recording_find_by_id)
        monkeypatch.setattr(users, "set_parental_pin_hash", recording_write)
        monkeypatch.setattr(hasher, "verify", recording_verify)
        monkeypatch.setattr(hasher, "hash", recording_hash)
        save = AsyncMock(wraps=users.save)
        monkeypatch.setattr(users, "save", save)

        await _use_case(fake_uow_factory, hasher).execute(
            SetParentalPinInput(user_id=str(user.id), current_password=_PASSWORD, pin=_PIN),
        )

        assert calls == [("read", True), ("verify", False), ("hash", False), ("write", True)]
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
                SetParentalPinInput(user_id=str(user.id), current_password=_PASSWORD, pin=_PIN),
            )

        assert exc_info.value.code == "USER_NOT_FOUND"


class TestSetParentalPinReauthentication:
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

        with pytest.raises(AccountPasswordInvalidError) as exc_info:
            await _use_case(fake_uow_factory, fake_password_hasher).execute(
                SetParentalPinInput(user_id=str(user.id), current_password="wrong", pin=_PIN),
            )

        assert exc_info.value.code == "ACCOUNT_PASSWORD_INVALID"
        write.assert_not_awaited()
        save.assert_not_awaited()
        assert (await _stored(fake_uow, user)).has_parental_pin is False

    def test_wrong_password_should_be_forbidden_not_unauthorized(self) -> None:
        # A 401 on this path would sign the user out on the frontend.
        error = AccountPasswordInvalidError(message="probe")

        assert isinstance(error, ForbiddenOperationException)
        assert not isinstance(error, UnauthorizedOperationException)

    async def test_account_without_password_hash_should_be_refused(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        user = User.create(email=Email("oauth@example.com"), hashed_password=None)
        async with fake_uow:
            user = await fake_uow.users.save(user)

        with pytest.raises(AccountPasswordInvalidError):
            await _use_case(fake_uow_factory, fake_password_hasher).execute(
                SetParentalPinInput(user_id=str(user.id), current_password="", pin=_PIN),
            )

        assert fake_password_hasher.verify_calls == []
        assert (await _stored(fake_uow, user)).has_parental_pin is False


class TestSetParentalPinValidation:
    @pytest.mark.parametrize(
        "pin", ["12345", "1234", "12a456", "\u0661\u0662\u0663\u0664\u0665\u0666"]
    )
    async def test_malformed_pin_should_fail_before_the_password_check(
        self,
        fake_uow: FakeIdentityUnitOfWork,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
        pin: str,
    ) -> None:
        user = await _seed(fake_uow, fake_password_hasher)

        with pytest.raises(DomainValidationException):
            await _use_case(fake_uow_factory, fake_password_hasher).execute(
                SetParentalPinInput(user_id=str(user.id), current_password=_PASSWORD, pin=pin),
            )

        assert fake_password_hasher.verify_calls == []
        assert (await _stored(fake_uow, user)).has_parental_pin is False

    async def test_unknown_user_should_raise_not_found(
        self,
        fake_uow_factory: FakeIdentityUnitOfWorkFactory,
        fake_password_hasher: FakePasswordHasher,
    ) -> None:
        with pytest.raises(UserNotFoundException):
            await _use_case(fake_uow_factory, fake_password_hasher).execute(
                SetParentalPinInput(
                    user_id=str(UserId.generate()), current_password=_PASSWORD, pin=_PIN
                ),
            )


class TestSetParentalPinInputRepr:
    def test_repr_should_not_contain_the_secrets(self) -> None:
        input_dto = SetParentalPinInput(
            user_id="usr_abcdefghijkl", current_password=_PASSWORD, pin=_PIN
        )

        assert _PASSWORD not in repr(input_dto)
        assert _PIN not in repr(input_dto)
