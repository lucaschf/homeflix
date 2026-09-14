"""End-to-end tests for the parental unlock routes (ADR-035, Amendment 7 D4/D9).

Drives ``POST`` and ``DELETE /api/v1/parental/unlock`` through the real app:
the per-device lockout as the client sees it (403, never 401, with the wait
in ``details[0].metadata``), closing the window without earning attempts,
a profile switch closing the window, the database defaults a FastAPI Users
login relies on, and the PIN staying out of responses and logs.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config.settings import get_settings
from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from tests.modules.identity.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
ME_PATH = "/api/v1/users/me"
PIN_PATH = "/api/v1/parental/pin"
UNLOCK_PATH = "/api/v1/parental/unlock"

_PIN = "904518"
_WRONG_PIN = "271828"
_MALFORMED_PIN = "90a51b"


async def _login(client: AsyncClient, user: SeededUser) -> str:
    response = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert response.status_code == 204
    token = client.cookies.get(get_settings().session_cookie_name)
    assert token is not None
    return token


async def _set_pin(client: AsyncClient, user: SeededUser) -> None:
    response = await client.put(PIN_PATH, json={"current_password": user.password, "pin": _PIN})
    assert response.status_code == 204, response.text


async def _row(session_factory: async_sessionmaker[AsyncSession], token: str) -> Row[Any]:
    async with session_factory() as session:
        result = await session.execute(
            select(
                AccessTokenModel.parental_failed_attempts,
                AccessTokenModel.parental_lockouts,
                AccessTokenModel.parental_locked_until,
                AccessTokenModel.parental_unlock_until,
            ).where(AccessTokenModel.token == token)
        )
        return result.one()


async def _unlock(client: AsyncClient, pin: object) -> tuple[int, dict[str, Any]]:
    response = await client.post(UNLOCK_PATH, json={"pin": pin})
    return response.status_code, (response.json() if response.content else {})


def _code(body: dict[str, Any]) -> str | None:
    return body.get("code")


@pytest.fixture
async def parent(
    client: AsyncClient,
    seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
) -> tuple[SeededUser, str]:
    """A logged-in account with a parental PIN, and its session token."""
    user = await seed_user_with_profile()
    token = await _login(client, user)
    await _set_pin(client, user)
    return user, token


class TestLoginDefaults:
    async def test_login_creates_a_session_with_zero_counters_and_no_windows(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        # FastAPI Users inserts only the token and the user, then refreshes:
        # the NOT NULL counters must have a server default in the model.
        user = await seed_user_with_profile()

        token = await _login(client, user)

        assert tuple(await _row(session_factory, token)) == (0, 0, None, None)


class TestUnlock:
    async def test_account_without_pin_is_409(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        token = await _login(client, user)

        status, body = await _unlock(client, _PIN)

        assert (status, _code(body)) == (409, "PARENTAL_PIN_NOT_CONFIGURED")
        assert (await _row(session_factory, token)).parental_failed_attempts == 0

    async def test_right_pin_is_204_and_opens_a_five_minute_window(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        parent: tuple[SeededUser, str],
    ) -> None:
        _, token = parent
        before = int(datetime.now(UTC).timestamp())

        status, _ = await _unlock(client, _PIN)

        after = int(datetime.now(UTC).timestamp())
        row = await _row(session_factory, token)
        assert status == 204
        assert row.parental_failed_attempts == 0
        assert before + 300 <= row.parental_unlock_until <= after + 300

    async def test_wrong_pin_is_403_never_401_and_keeps_the_session(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        parent: tuple[SeededUser, str],
    ) -> None:
        _, token = parent

        status, body = await _unlock(client, _WRONG_PIN)

        assert (status, _code(body)) == (403, "PARENTAL_PIN_INVALID")
        assert (await _row(session_factory, token)).parental_failed_attempts == 1
        assert (await client.get(ME_PATH)).status_code == 200

    async def test_fifth_wrong_pin_locks_the_device_with_the_wait_in_details(
        self,
        client: AsyncClient,
        parent: tuple[SeededUser, str],
    ) -> None:
        attempts = [await _unlock(client, _WRONG_PIN) for _ in range(5)]
        sixth_status, sixth = await _unlock(client, _PIN)

        assert [(s, _code(b)) for s, b in attempts] == [(403, "PARENTAL_PIN_INVALID")] * 4 + [
            (403, "PARENTAL_PIN_LOCKED")
        ]
        assert (sixth_status, _code(sixth)) == (403, "PARENTAL_PIN_LOCKED")
        # A real clock runs between the attempts; the integration tests pin
        # the exact value with a controlled one.
        for body in (attempts[-1][1], sixth):
            wait = body["details"][0]["metadata"]["retry_after_seconds"]
            assert 290 <= wait <= 300

    @pytest.mark.parametrize(
        "pin",
        [
            pytest.param(_MALFORMED_PIN, id="letters"),
            pytest.param("9045", id="four-digits"),
            pytest.param(904518, id="json-number"),
        ],
    )
    async def test_malformed_pin_is_422_without_echo_or_attempt(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        parent: tuple[SeededUser, str],
        pin: object,
    ) -> None:
        _, token = parent

        response = await client.post(UNLOCK_PATH, json={"pin": pin})

        assert response.status_code == 422
        assert str(pin) not in response.text
        assert (await _row(session_factory, token)).parental_failed_attempts == 0

    @pytest.mark.parametrize("method", ["POST", "DELETE"])
    async def test_routes_require_a_session(self, client: AsyncClient, method: str) -> None:
        response = await client.request(method, UNLOCK_PATH, json={"pin": _PIN})

        assert response.status_code == 401


class TestLock:
    async def test_delete_closes_the_window(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        parent: tuple[SeededUser, str],
    ) -> None:
        _, token = parent
        assert (await _unlock(client, _PIN))[0] == 204

        response = await client.delete(UNLOCK_PATH)

        assert response.status_code == 204
        assert (await _row(session_factory, token)).parental_unlock_until is None

    async def test_closing_the_window_earns_no_attempts(
        self,
        client: AsyncClient,
        parent: tuple[SeededUser, str],
    ) -> None:
        for _ in range(4):
            assert (await _unlock(client, _WRONG_PIN))[0] == 403

        assert (await client.delete(UNLOCK_PATH)).status_code == 204
        status, body = await _unlock(client, _WRONG_PIN)

        assert (status, _code(body)) == (403, "PARENTAL_PIN_LOCKED")


class TestSwitchClosesTheWindow:
    async def test_switching_profile_after_unlock_closes_the_window(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        parent: tuple[SeededUser, str],
    ) -> None:
        user, token = parent
        assert (await _unlock(client, _PIN))[0] == 204
        assert (await _row(session_factory, token)).parental_unlock_until is not None

        response = await client.post(f"/api/v1/profiles/{user.profile_external_id}/switch")

        assert response.status_code == 204
        assert (await _row(session_factory, token)).parental_unlock_until is None

    async def test_switching_profile_earns_no_attempts(
        self,
        client: AsyncClient,
        parent: tuple[SeededUser, str],
    ) -> None:
        """Switching must not earn attempts: wrong PINs and switches cannot alternate."""
        created = await client.post("/api/v1/profiles", json={"name": "Kids"})
        assert created.status_code == 201, created.text
        for _ in range(4):
            assert (await _unlock(client, _WRONG_PIN))[0] == 403

        response = await client.post(f"/api/v1/profiles/{created.json()['data']['id']}/switch")
        assert response.status_code == 204
        status, body = await _unlock(client, _WRONG_PIN)

        assert (status, _code(body)) == (403, "PARENTAL_PIN_LOCKED")


class TestPinStaysOutOfLogs:
    async def test_unlock_attempts_do_not_log_the_pin(
        self,
        client: AsyncClient,
        parent: tuple[SeededUser, str],
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # structlog prints to stdout (PrintLoggerFactory), which ``caplog``
        # does not see; stdlib loggers go to ``caplog``. Both are checked.
        caplog.set_level(logging.DEBUG)
        capsys.readouterr()  # drop output from seeding, login and PIN setup

        statuses = [
            (await _unlock(client, _WRONG_PIN))[0],
            (await _unlock(client, _MALFORMED_PIN))[0],
            (await _unlock(client, _PIN))[0],
        ]
        for _ in range(4):
            statuses.append((await _unlock(client, _WRONG_PIN))[0])

        assert statuses == [403, 422, 204, 403, 403, 403, 403]
        captured = capsys.readouterr()
        logged = captured.out + captured.err + caplog.text
        assert "Handled core exception" in logged
        for secret in (_PIN, _WRONG_PIN, _MALFORMED_PIN):
            assert secret not in logged
