"""End-to-end tests for the member-facing settings routes."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from src.modules.settings.domain.value_objects import AvatarConfig
from tests.modules.settings.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
AVATAR_LIMITS_PATH = "/api/v1/settings/avatar"
ADMIN_AVATAR_PATH = "/api/v1/admin/settings/avatar"


async def _login(client: AsyncClient, user: SeededUser) -> None:
    resp = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert resp.status_code == 204


@pytest.mark.e2e
class TestAvatarLimits:
    """``GET /api/v1/settings/avatar`` — the cap a member's client needs."""

    async def test_should_return_401_when_unauthenticated(self, client: AsyncClient) -> None:
        response = await client.get(AVATAR_LIMITS_PATH)

        assert response.status_code == 401

    async def test_should_serve_a_member_the_defaults(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        # Not admin-gated on purpose: a member uploading their own
        # avatar has to know the cap to check the file locally.
        member = await seed_user_with_profile(email="member@example.com", is_admin=False)
        await _login(client, member)

        response = await client.get(AVATAR_LIMITS_PATH)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["type"] == "avatar_limits"
        assert body["data"] == {
            "max_size_bytes": 2 * 1024 * 1024,
            "max_size_mb": 2,
            "size_pixels": 256,
        }

    async def test_should_not_expose_the_storage_subdir(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com", is_admin=False)
        await _login(client, member)

        response = await client.get(AVATAR_LIMITS_PATH)

        assert "storage_subdir" not in response.json()["data"]

    async def test_should_reflect_an_admin_edit(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        # The route reads the ``RuntimeSettings`` snapshot the upload path
        # enforces, and the admin write invalidates it — so the advertised
        # cap follows the edit instead of lagging by the TTL.
        admin = await seed_user_with_profile(email="admin@example.com", is_admin=True)
        await _login(client, admin)

        patch = await client.patch(
            ADMIN_AVATAR_PATH,
            json=AvatarConfig(max_size_mb=9, size_pixels=512).model_dump(mode="json"),
        )
        assert patch.status_code == 200, patch.text

        response = await client.get(AVATAR_LIMITS_PATH)

        assert response.json()["data"] == {
            "max_size_bytes": 9 * 1024 * 1024,
            "max_size_mb": 9,
            "size_pixels": 512,
        }
