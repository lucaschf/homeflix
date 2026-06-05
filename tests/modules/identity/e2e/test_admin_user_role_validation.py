"""End-to-end tests for role validation at the admin user endpoints.

``role`` is typed with the ``UserRole`` enum in the request schemas
(ADR-018), so an invalid role must be rejected as a 422 at the HTTP
boundary — with the allowed values in the OpenAPI schema — instead of
travelling into the use case as a raw string.
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from tests.modules.identity.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
ADMIN_USERS_PATH = "/api/v1/admin/users"


async def _login(client: AsyncClient, user: SeededUser) -> None:
    response = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert response.status_code in (200, 204)


@pytest.mark.e2e
class TestAdminUserRoleValidation:
    async def test_create_should_reject_unknown_role_with_422(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        admin = await seed_user_with_profile(is_admin=True)
        await _login(client, admin)

        response = await client.post(
            ADMIN_USERS_PATH,
            json={
                "email": "new@homeflix.local",
                "password": "initial-pass-123",
                "role": "superadmin",
            },
        )

        assert response.status_code == 422

    async def test_update_should_reject_unknown_role_with_422(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        admin = await seed_user_with_profile(is_admin=True)
        await _login(client, admin)

        response = await client.patch(
            f"{ADMIN_USERS_PATH}/usr_aaaaaaaaaaaa",
            json={"role": "adminn"},
        )

        assert response.status_code == 422

    async def test_list_should_reject_unknown_role_filter_with_422(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        admin = await seed_user_with_profile(is_admin=True)
        await _login(client, admin)

        response = await client.get(ADMIN_USERS_PATH, params={"role": "bogus"})

        assert response.status_code == 422

    async def test_create_should_accept_valid_role(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        admin = await seed_user_with_profile(is_admin=True)
        await _login(client, admin)

        response = await client.post(
            ADMIN_USERS_PATH,
            json={
                "email": "fresh@homeflix.local",
                "password": "initial-pass-123",
                "role": "admin",
            },
        )

        assert response.status_code == 201
        assert response.json()["data"]["role"] == "admin"
