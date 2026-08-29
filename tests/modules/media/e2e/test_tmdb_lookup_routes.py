"""End-to-end tests for ``GET /api/v1/catalog/lookup``."""

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import AsyncClient

from src.modules.metadata.application.ports.metadata_provider_port import SearchCandidate
from tests.modules.media.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
LOOKUP_PATH = "/api/v1/catalog/lookup"


async def _login(client: AsyncClient, user: SeededUser) -> None:
    resp = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert resp.status_code == 204


def _override_tmdb_client(app: FastAPI, fake: AsyncMock) -> None:
    """Swap the real TMDB client for a mock so the e2e doesn't hit the network."""
    app.state.container.media.tmdb_client.override(providers.Object(fake))


@pytest.mark.e2e
class TestTmdbLookupAuth:
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(LOOKUP_PATH, params={"q": "matrix"})
        assert resp.status_code == 401


@pytest.mark.e2e
class TestTmdbLookupRouting:
    async def test_plain_text_returns_combined_candidates(
        self,
        app: FastAPI,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        fake = AsyncMock()
        fake.find_movie_candidates.return_value = [
            SearchCandidate(
                tmdb_id=603,
                media_type="movie",
                title="The Matrix",
                year=1999,
                overview="A hacker…",
                poster_url="https://image.tmdb.org/m.jpg",
            ),
        ]
        fake.find_series_candidates.return_value = []
        _override_tmdb_client(app, fake)

        user = await seed_user_with_profile(email="u@example.com", is_admin=False)
        await _login(client, user)
        resp = await client.get(LOOKUP_PATH, params={"q": "matrix"})

        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert payload["kind"] == "text"
        assert payload["query"] == "matrix"
        assert len(payload["candidates"]) == 1
        assert payload["candidates"][0]["tmdb_id"] == 603

    async def test_tmdb_movie_url_calls_movie_summary_only(
        self,
        app: FastAPI,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        fake = AsyncMock()
        fake.get_movie_summary_by_id.return_value = SearchCandidate(
            tmdb_id=603,
            media_type="movie",
            title="The Matrix",
            year=1999,
            overview=None,
            poster_url=None,
        )
        _override_tmdb_client(app, fake)

        user = await seed_user_with_profile(email="u@example.com", is_admin=False)
        await _login(client, user)
        resp = await client.get(
            LOOKUP_PATH,
            params={"q": "https://www.themoviedb.org/movie/603-the-matrix"},
        )

        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert payload["kind"] == "tmdb_id"
        assert len(payload["candidates"]) == 1
        assert payload["candidates"][0]["media_type"] == "movie"
        fake.get_movie_summary_by_id.assert_awaited_once_with(603)
        fake.get_series_summary_by_id.assert_not_called()
        fake.find_movie_candidates.assert_not_called()

    async def test_imdb_id_calls_find(
        self,
        app: FastAPI,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        fake = AsyncMock()
        fake.find_by_imdb_id.return_value = [
            SearchCandidate(
                tmdb_id=603,
                media_type="movie",
                title="The Matrix",
                year=1999,
                overview=None,
                poster_url=None,
            ),
        ]
        _override_tmdb_client(app, fake)

        user = await seed_user_with_profile(email="u@example.com", is_admin=False)
        await _login(client, user)
        resp = await client.get(LOOKUP_PATH, params={"q": "tt0133093"})

        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert payload["kind"] == "imdb_id"
        fake.find_by_imdb_id.assert_awaited_once_with("tt0133093")

    async def test_empty_q_returns_422(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile(email="u@example.com", is_admin=False)
        await _login(client, user)
        resp = await client.get(LOOKUP_PATH, params={"q": ""})
        assert resp.status_code == 422

    async def test_limit_above_max_returns_422(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile(email="u@example.com", is_admin=False)
        await _login(client, user)
        resp = await client.get(LOOKUP_PATH, params={"q": "matrix", "limit": 999})
        assert resp.status_code == 422
