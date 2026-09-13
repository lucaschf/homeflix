"""End-to-end tests for the auth gate on the person-bio route.

``GET /api/v1/people/{tmdb_id}`` proxies TMDB. The web client only calls
it from the actor page, which sits behind its auth guard, so the route
requires a signed-in user of any role. The TMDB client is swapped for a
mock so the tests can also prove an anonymous request never reaches the
provider.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from unittest.mock import AsyncMock

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import AsyncClient

from src.modules.metadata.application.ports.metadata_provider_port import (
    MetadataProvider,
    PersonMetadata,
)
from tests.modules.metadata.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
PERSON_PATH = "/api/v1/people/6193"


@pytest.fixture
async def provider(app: FastAPI) -> AsyncGenerator[AsyncMock, None]:
    """Replace the TMDB client with a mock that knows one person."""
    mock = AsyncMock(spec=MetadataProvider)
    mock.get_person.return_value = PersonMetadata(
        tmdb_id=6193,
        name="Leonardo DiCaprio",
        biography="An American actor.",
        known_for_department="Acting",
    )
    app.state.container.metadata.tmdb_client.override(providers.Object(mock))
    yield mock
    app.state.container.metadata.tmdb_client.reset_override()


async def _login(
    client: AsyncClient,
    seed: Callable[..., Awaitable[SeededUser]],
    *,
    is_admin: bool,
) -> None:
    user = await seed(
        email="admin@example.com" if is_admin else "member@example.com",
        is_admin=is_admin,
    )
    response = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert response.status_code == 204


@pytest.mark.e2e
class TestGetPersonAuth:
    """Any signed-in user may read a bio; anonymous callers may not."""

    async def test_anonymous_caller_gets_401_without_calling_the_provider(
        self, client: AsyncClient, provider: AsyncMock
    ) -> None:
        response = await client.get(PERSON_PATH)

        assert response.status_code == 401
        provider.get_person.assert_not_awaited()

    @pytest.mark.parametrize("is_admin", [False, True], ids=["member", "admin"])
    async def test_signed_in_user_gets_the_bio(
        self,
        client: AsyncClient,
        provider: AsyncMock,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        is_admin: bool,
    ) -> None:
        await _login(client, seed_user_with_profile, is_admin=is_admin)

        response = await client.get(PERSON_PATH, params={"lang": "pt-BR"})

        assert response.status_code == 200
        person = response.json()["data"]
        assert person["tmdb_id"] == 6193
        assert person["name"] == "Leonardo DiCaprio"
        assert person["biography"] == "An American actor."
        provider.get_person.assert_awaited_once_with(6193, language="pt-BR")
