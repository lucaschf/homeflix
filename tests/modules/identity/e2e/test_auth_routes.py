"""End-to-end tests for the cookie auth router.

Drives ``POST /api/v1/auth/cookie/login``, ``POST /api/v1/auth/cookie/logout``,
and ``GET /api/v1/users/me`` over an in-process ASGI transport. Verifies
the cookie + DB-row contract documented in ADR-011.
"""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from tests.modules.identity.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
LOGOUT_PATH = "/api/v1/auth/cookie/logout"
ME_PATH = "/api/v1/users/me"
COOKIE_NAME = "homeflix_session"


async def _count_session_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    async with session_factory() as session:
        result = await session.execute(select(AccessTokenModel))
        return len(result.scalars().all())


class TestLogin:
    async def test_should_return_204_and_set_session_cookie_on_valid_credentials(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()

        response = await client.post(
            LOGIN_PATH,
            data={"username": user.email, "password": user.password},
        )

        assert response.status_code == 204
        assert COOKIE_NAME in response.cookies

    async def test_should_persist_an_access_token_row_after_login(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()

        await client.post(
            LOGIN_PATH,
            data={"username": user.email, "password": user.password},
        )

        assert await _count_session_rows(session_factory) == 1

    async def test_should_set_httponly_and_strict_samesite_on_the_cookie(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()

        response = await client.post(
            LOGIN_PATH,
            data={"username": user.email, "password": user.password},
        )

        # httpx exposes the raw Set-Cookie header so we can assert flags.
        set_cookie = response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie
        assert "samesite=strict" in set_cookie.lower()

    async def test_should_return_400_for_unknown_email(
        self,
        client: AsyncClient,
    ):
        response = await client.post(
            LOGIN_PATH,
            data={"username": "ghost@nowhere.com", "password": "anything"},
        )

        assert response.status_code == 400

    async def test_should_return_400_for_wrong_password(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()

        response = await client.post(
            LOGIN_PATH,
            data={"username": user.email, "password": "definitely-wrong"},
        )

        assert response.status_code == 400


class TestLogout:
    async def test_should_return_204_and_delete_the_session_row(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()
        await client.post(
            LOGIN_PATH,
            data={"username": user.email, "password": user.password},
        )
        assert await _count_session_rows(session_factory) == 1

        response = await client.post(LOGOUT_PATH)

        assert response.status_code == 204
        assert await _count_session_rows(session_factory) == 0

    async def test_should_return_401_when_no_session_cookie_is_present(
        self,
        client: AsyncClient,
    ):
        response = await client.post(LOGOUT_PATH)

        # FastAPI Users rejects logout without a session.
        assert response.status_code == 401


class TestProtectedRoute:
    async def test_should_return_401_when_calling_users_me_without_cookie(
        self,
        client: AsyncClient,
    ):
        response = await client.get(ME_PATH)

        assert response.status_code == 401

    async def test_should_return_user_payload_with_prefixed_external_id_when_logged_in(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile(email="lucas@homeflix.local")
        await client.post(
            LOGIN_PATH,
            data={"username": user.email, "password": user.password},
        )

        response = await client.get(ME_PATH)

        assert response.status_code == 200
        body = response.json()
        # api_single envelope: {"type": "user", "data": {...}}
        assert body["type"] == "user"
        payload = body["data"]
        assert payload["id"] == user.user_external_id
        assert payload["id"].startswith("usr_")
        assert payload["email"] == "lucas@homeflix.local"
