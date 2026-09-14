"""End-to-end tests for the parental PIN routes (ADR-035, Amendment 7 D3/D4).

Drives ``PUT /api/v1/parental/pin`` and ``POST /api/v1/parental/pin/remove``
through the real app: account-password re-authentication, the 403 (never
401) for a wrong password, the ``parental_pin_configured`` flag on
``/users/me``, and the rule that neither the PIN, the password nor the
stored hash leaves the server — in a response body or in a log line.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fastapi_users.password import PasswordHelper
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from tests.modules.identity.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
ME_PATH = "/api/v1/users/me"
PIN_PATH = "/api/v1/parental/pin"
REMOVE_PATH = "/api/v1/parental/pin/remove"

_PIN = "904518"
_MALFORMED_PIN = "90a51b"


async def _login(client: AsyncClient, user: SeededUser) -> None:
    response = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert response.status_code == 204


async def _pin_configured(client: AsyncClient) -> bool:
    response = await client.get(ME_PATH)
    assert response.status_code == 200
    configured = response.json()["data"]["parental_pin_configured"]
    assert isinstance(configured, bool)
    return configured


async def _set_pin(client: AsyncClient, user: SeededUser, pin: str = _PIN) -> None:
    response = await client.put(PIN_PATH, json={"current_password": user.password, "pin": pin})
    assert response.status_code == 204, response.text


async def _stored_hash(
    session_factory: async_sessionmaker[AsyncSession], user: SeededUser
) -> str | None:
    async with session_factory() as session:
        return await session.scalar(
            select(UserModel.parental_pin_hash).where(
                UserModel.external_id == user.user_external_id
            )
        )


class TestParentalPinLifecycle:
    async def test_me_should_add_only_the_parental_fields_to_its_shape(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.get(ME_PATH)

        assert set(response.json()["data"]) == {
            "id",
            "email",
            "role",
            "is_active",
            "is_verified",
            "active_profile_id",
            "parental_pin_configured",
            "admin_access",
        }
        assert response.json()["data"]["parental_pin_configured"] is False

    async def test_set_then_remove_should_flip_the_flag(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)
        assert await _pin_configured(client) is False

        await _set_pin(client, user)
        assert await _pin_configured(client) is True

        removed = await client.post(REMOVE_PATH, json={"current_password": user.password})
        assert removed.status_code == 204
        assert await _pin_configured(client) is False

    async def test_setting_again_should_replace_the_pin(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)
        await _set_pin(client, user, pin="111111")

        await _set_pin(client, user, pin=_PIN)

        stored = await _stored_hash(session_factory, user)
        assert stored is not None
        assert PasswordHelper().verify_and_update(_PIN, stored)[0] is True
        assert PasswordHelper().verify_and_update("111111", stored)[0] is False

    async def test_the_stored_value_should_be_a_hash_of_the_pin(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)

        await _set_pin(client, user)

        stored = await _stored_hash(session_factory, user)
        assert stored is not None
        assert _PIN not in stored
        assert PasswordHelper().verify_and_update(_PIN, stored)[0] is True

    async def test_the_hash_should_never_appear_in_a_response(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        admin = await seed_user_with_profile(email="admin@example.com", is_admin=True)
        await _login(client, admin)
        await _set_pin(client, admin)
        stored = await _stored_hash(session_factory, admin)
        assert stored is not None

        for path in (
            ME_PATH,
            "/api/v1/admin/users",
            f"/api/v1/admin/users/{admin.user_external_id}",
        ):
            response = await client.get(path)
            assert response.status_code == 200, path
            assert stored not in response.text, path
            assert "parental_pin_hash" not in response.text, path


class TestParentalPinReauthentication:
    async def test_set_with_a_wrong_password_should_be_403_not_401(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.put(
            PIN_PATH, json={"current_password": "not-the-password", "pin": _PIN}
        )

        assert response.status_code == 403
        assert response.json()["code"] == "ACCOUNT_PASSWORD_INVALID"
        assert await _pin_configured(client) is False

    async def test_remove_with_a_wrong_password_should_be_403_not_401(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)
        await _set_pin(client, user)

        response = await client.post(REMOVE_PATH, json={"current_password": "not-the-password"})

        assert response.status_code == 403
        assert response.json()["code"] == "ACCOUNT_PASSWORD_INVALID"
        assert await _pin_configured(client) is True

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("PUT", PIN_PATH, {"current_password": "x", "pin": _PIN}),
            ("POST", REMOVE_PATH, {"current_password": "x"}),
        ],
    )
    async def test_routes_should_require_a_session(
        self, client: AsyncClient, method: str, path: str, body: dict[str, Any]
    ) -> None:
        response = await client.request(method, path, json=body)

        assert response.status_code == 401


class TestParentalPinValidation:
    @pytest.mark.parametrize(
        "pin",
        [
            pytest.param(_MALFORMED_PIN, id="letters"),
            pytest.param("9045", id="four-digits"),
            pytest.param("٩٠٤٥١٨", id="arabic-indic-digits"),
            pytest.param(904518, id="json-number"),
        ],
    )
    async def test_malformed_pin_should_be_422_without_echoing_it(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        pin: object,
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.put(PIN_PATH, json={"current_password": user.password, "pin": pin})

        assert response.status_code == 422
        assert str(pin) not in response.text
        assert user.password not in response.text
        assert await _pin_configured(client) is False


class TestParentalPinSecretsStayOutOfLogs:
    async def test_set_and_remove_should_not_log_the_pin_or_the_password(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # structlog prints to stdout (PrintLoggerFactory), which ``caplog``
        # does not see; stdlib loggers go to ``caplog``. Both are checked.
        caplog.set_level(logging.DEBUG)
        user = await seed_user_with_profile()
        await _login(client, user)
        capsys.readouterr()  # drop output from seeding and login

        await _set_pin(client, user)
        wrong_password = await client.put(
            PIN_PATH, json={"current_password": "wrong-horse-battery", "pin": _PIN}
        )
        malformed = await client.put(
            PIN_PATH, json={"current_password": user.password, "pin": _MALFORMED_PIN}
        )
        wrong_removal = await client.post(
            REMOVE_PATH, json={"current_password": "wrong-horse-battery"}
        )
        removed = await client.post(REMOVE_PATH, json={"current_password": user.password})

        assert [r.status_code for r in (wrong_password, malformed, wrong_removal, removed)] == [
            403,
            422,
            403,
            204,
        ]
        captured = capsys.readouterr()
        logged = captured.out + captured.err + caplog.text
        # The capture really sees the handlers' log lines, so the absence
        # checks below cannot pass on an empty buffer.
        assert "Handled core exception" in logged
        for secret in (_PIN, _MALFORMED_PIN, user.password, "wrong-horse-battery"):
            assert secret not in logged
