"""End-to-end tests for the member catalog-request routes (ADR-022 B3)."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from tests.modules.catalog_requests.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
ROOT = "/api/v1/catalog-requests"
_TMDB = 348


async def _login(client: AsyncClient, user: SeededUser) -> None:
    resp = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert resp.status_code == 204


async def _subscribe(client: AsyncClient, tmdb_id: int = _TMDB) -> None:
    resp = await client.post(
        f"{ROOT}/{tmdb_id}/notify",
        json={"media_type": "movie", "title": "Alien"},
    )
    assert resp.status_code == 200


@pytest.mark.e2e
class TestCatalogRequestMemberRoutes:
    """The "Em breve" feed + the unsubscribe toggle."""

    async def test_unauthenticated_feed_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(ROOT)
        assert response.status_code == 401

    async def test_feed_shows_count_and_subscription(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile()
        await _login(client, member)
        await _subscribe(client)

        response = await client.get(ROOT)

        assert response.status_code == 200
        items = response.json()["data"]
        item = next(i for i in items if i["tmdb_id"] == _TMDB)
        assert item["subscriber_count"] == 1
        assert item["is_subscribed"] is True
        assert item["status"] == "pending"
        assert item["source"] == "user"

    async def test_unsubscribe_drops_the_caller(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile()
        await _login(client, member)
        await _subscribe(client)

        resp = await client.delete(f"{ROOT}/{_TMDB}/notify", params={"media_type": "movie"})
        assert resp.status_code == 200

        feed = await client.get(ROOT)
        item = next(i for i in feed.json()["data"] if i["tmdb_id"] == _TMDB)
        assert item["is_subscribed"] is False
        assert item["subscriber_count"] == 0

    async def test_unsubscribe_unknown_returns_404(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile()
        await _login(client, member)

        resp = await client.delete(f"{ROOT}/999999/notify", params={"media_type": "movie"})

        assert resp.status_code == 404
