"""End-to-end tests for the admin catalog-request routes (ADR-022 B4)."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from tests.modules.catalog_requests.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
ROOT = "/api/v1/catalog-requests"
ADMIN_ROOT = "/api/v1/admin/catalog-requests"
_TMDB = 348


async def _login(client: AsyncClient, user: SeededUser) -> None:
    resp = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert resp.status_code == 204


@pytest.mark.e2e
class TestAdminCatalogRequestRoutes:
    """The admin queue (subscriber counts) + the include action."""

    async def test_member_cannot_access_admin_queue(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile()
        await _login(client, member)

        assert (await client.get(ADMIN_ROOT)).status_code == 403

    async def test_queue_shows_count_then_include_archives(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com")
        admin = await seed_user_with_profile(email="admin@example.com", is_admin=True)

        # Member subscribes to a missing title.
        await _login(client, member)
        sub = await client.post(
            f"{ROOT}/{_TMDB}/notify",
            json={"media_type": "movie", "title": "Alien"},
        )
        assert sub.status_code == 200

        # Admin sees it in the queue with the subscriber count.
        await _login(client, admin)
        queue = await client.get(ADMIN_ROOT)
        item = next(i for i in queue.json()["data"] if i["tmdb_id"] == _TMDB)
        assert item["subscriber_count"] == 1
        assert item["status"] == "pending"
        assert item["source"] == "user"
        request_id = item["id"]

        # Admin marks it included → fulfilled + dropped from the queue.
        included = await client.post(f"{ADMIN_ROOT}/{request_id}/include")
        assert included.status_code == 200
        assert included.json()["data"]["is_fulfilled"] is True

        after = await client.get(ADMIN_ROOT)
        assert all(i["tmdb_id"] != _TMDB for i in after.json()["data"])

    async def test_include_unknown_returns_404(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        admin = await seed_user_with_profile(is_admin=True)
        await _login(client, admin)

        resp = await client.post(f"{ADMIN_ROOT}/req_missing00000/include")

        assert resp.status_code == 404
