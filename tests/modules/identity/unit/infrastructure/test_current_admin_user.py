"""Unit tests for the admin route guards (ADR-035, Amendment 7).

``current_admin_user`` checks the role first, returns without touching the
container when the account has no parental PIN, and otherwise hands the
request to ``ensure_admin_authority``. ``authenticated_user`` reports
``is_admin`` from the same decision, and ``authenticated_admin`` never asks
the gate a second time.
"""

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from src.building_blocks.application.errors import ForbiddenOperationException
from src.config.settings import get_settings
from src.modules.identity.application.dtos.identity_dtos import (
    AdminAccessLevel,
    GetAdminAccessInput,
)
from src.modules.identity.domain.errors import ParentalPinRequiredError
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.auth.fastapi_users import (
    authenticated_admin,
    authenticated_user,
    current_admin_user,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel

pytestmark = pytest.mark.unit

_TOKEN = "session-token-abc"


def _make_user(role: str, *, pin_hash: str | None = None) -> UserModel:
    """Build a minimal ``UserModel`` for the dep call.

    Only attributes the guards actually inspect matter — the rest of
    the SQLAlchemy machinery (PK, hashed password, timestamps) is
    irrelevant here.
    """
    user = UserModel()
    user.id = uuid.uuid4()
    user.external_id = "usr_test"
    user.email = "user@example.com"
    user.hashed_password = "x"
    user.is_active = True
    user.is_superuser = role == UserRole.ADMIN.value
    user.is_verified = True
    user.role = role
    user.parental_pin_hash = pin_hash
    return user


class _Identity:
    """Stand-in for ``container.identity`` recording which providers were built."""

    def __init__(self, *, access: AdminAccessLevel = AdminAccessLevel.GRANTED) -> None:
        self.ensure = SimpleNamespace(execute=AsyncMock(return_value=None))
        self.get = SimpleNamespace(execute=AsyncMock(return_value=access))
        self.ensure_admin_authority = MagicMock(return_value=self.ensure)
        self.get_admin_access = MagicMock(return_value=self.get)

    @property
    def built(self) -> bool:
        return self.ensure_admin_authority.called or self.get_admin_access.called


def _request(identity: _Identity, *, method: str = "GET", cookie: bool = True) -> Request:
    app = SimpleNamespace(state=SimpleNamespace(container=SimpleNamespace(identity=identity)))
    headers: list[tuple[bytes, bytes]] = []
    if cookie:
        headers.append((b"cookie", f"{get_settings().session_cookie_name}={_TOKEN}".encode()))
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": "/api/v1/admin/anything",
        "headers": headers,
        "app": app,
    }
    return Request(scope)


def _sent_input(mock: AsyncMock) -> GetAdminAccessInput:
    mock.assert_awaited_once()
    (sent,) = mock.await_args.args
    return sent


class TestCurrentAdminUser:
    async def test_should_raise_admin_required_for_a_member_without_building_the_gate(
        self,
    ) -> None:
        # Role first: a member must learn nothing about the account's PIN.
        identity = _Identity()
        user = _make_user(UserRole.MEMBER.value, pin_hash="$argon2id$pin")

        with pytest.raises(ForbiddenOperationException) as exc_info:
            await current_admin_user(request=_request(identity, method="POST"), user=user)

        assert exc_info.value.code == "FORBIDDEN"
        assert exc_info.value.message_code == "ADMIN_REQUIRED"
        assert exc_info.value.required_permission == "admin"
        assert not identity.built

    @pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
    async def test_should_return_an_admin_without_pin_without_building_the_gate(
        self, method: str
    ) -> None:
        identity = _Identity()
        user = _make_user(UserRole.ADMIN.value)

        result = await current_admin_user(request=_request(identity, method=method), user=user)

        assert result is user
        assert not identity.built

    @pytest.mark.parametrize(
        ("method", "is_write"),
        [
            ("GET", False),
            ("HEAD", False),
            ("OPTIONS", False),
            ("POST", True),
            ("PUT", True),
            ("PATCH", True),
            ("DELETE", True),
        ],
    )
    async def test_should_ask_the_gate_for_an_admin_with_pin(
        self, method: str, is_write: bool
    ) -> None:
        identity = _Identity()
        user = _make_user(UserRole.ADMIN.value, pin_hash="$argon2id$pin")

        result = await current_admin_user(request=_request(identity, method=method), user=user)

        assert result is user
        assert not identity.get_admin_access.called
        sent = _sent_input(identity.ensure.execute)
        assert sent == GetAdminAccessInput(
            user_id="usr_test",
            role=UserRole.ADMIN,
            parental_pin_configured=True,
            session_token=_TOKEN,
            is_write=is_write,
        )

    async def test_should_propagate_the_suspension_as_pin_required(self) -> None:
        identity = _Identity()
        identity.ensure.execute.side_effect = ParentalPinRequiredError(message="suspended")
        user = _make_user(UserRole.ADMIN.value, pin_hash="$argon2id$pin")

        with pytest.raises(ParentalPinRequiredError):
            await current_admin_user(request=_request(identity, method="POST"), user=user)

    async def test_should_await_a_provider_that_resolves_asynchronously(self) -> None:
        # ``session_factory`` is an async Resource in production, so the
        # provider hands back an awaitable rather than the use case.
        identity = _Identity()
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        future.set_result(identity.ensure)
        identity.ensure_admin_authority.return_value = future
        user = _make_user(UserRole.ADMIN.value, pin_hash="$argon2id$pin")

        await current_admin_user(request=_request(identity), user=user)

        identity.ensure.execute.assert_awaited_once()

    async def test_should_send_an_empty_token_rather_than_401_without_cookie(self) -> None:
        # The cookie is the only transport, so this cannot happen after
        # ``current_active_user``; if it did, no session matches and the gate
        # suspends (403) instead of signing the client out.
        identity = _Identity()
        user = _make_user(UserRole.ADMIN.value, pin_hash="$argon2id$pin")

        await current_admin_user(request=_request(identity, cookie=False), user=user)

        assert _sent_input(identity.ensure.execute).session_token == ""


class TestAuthenticatedUser:
    async def test_member_is_not_admin_and_builds_nothing(self) -> None:
        identity = _Identity()
        user = _make_user(UserRole.MEMBER.value, pin_hash="$argon2id$pin")

        caller = await authenticated_user(request=_request(identity), user=user)

        assert (caller.external_id, caller.is_admin) == ("usr_test", False)
        assert not identity.built

    async def test_admin_without_pin_is_admin_and_builds_nothing(self) -> None:
        identity = _Identity()

        caller = await authenticated_user(
            request=_request(identity), user=_make_user(UserRole.ADMIN.value)
        )

        assert caller.is_admin is True
        assert not identity.built

    @pytest.mark.parametrize(
        ("access", "is_admin"),
        [(AdminAccessLevel.GRANTED, True), (AdminAccessLevel.SUSPENDED, False)],
    )
    @pytest.mark.parametrize("method", ["GET", "POST"])
    async def test_admin_with_pin_is_admin_only_with_read_authority(
        self, access: AdminAccessLevel, is_admin: bool, method: str
    ) -> None:
        identity = _Identity(access=access)
        user = _make_user(UserRole.ADMIN.value, pin_hash="$argon2id$pin")

        caller = await authenticated_user(request=_request(identity, method=method), user=user)

        assert caller.is_admin is is_admin
        assert not identity.ensure_admin_authority.called
        assert _sent_input(identity.get.execute).is_write is False


class TestAuthenticatedAdmin:
    async def test_projects_the_admin_without_asking_the_gate_again(self) -> None:
        # ``current_admin_user`` already decided; a second evaluation would
        # repeat the gate's queries on every one of the 73 routes.
        user = _make_user(UserRole.ADMIN.value, pin_hash="$argon2id$pin")

        caller = await authenticated_admin(user=user)

        assert (caller.external_id, caller.is_admin) == ("usr_test", True)
