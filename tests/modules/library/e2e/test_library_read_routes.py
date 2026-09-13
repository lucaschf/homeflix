"""End-to-end tests for the auth gate on the library read routes.

``LibraryOutput`` carries the absolute on-disk ``paths`` of every root
folder. The two reads split on who needs them:

- ``GET /api/v1/libraries`` backs the admin pages *and* the profile
  editor (``/profiles/manage``), which members reach too — so any
  signed-in user may list, but only an admin sees ``paths``. A member
  gets ``paths: []``, keeping the ``string[]`` shape the web client
  types and renders.
- ``GET /api/v1/libraries/{library_id}`` only backs the admin library
  editor, so it is admin-only.

Members log in without switching to a profile on purpose: the profile
editor is reachable straight from the picker, before one is chosen.
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.value_objects.library_type import LibraryType
from src.modules.library.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyLibraryUnitOfWorkFactory,
)
from tests.modules.library.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
LIBRARIES_PATH = "/api/v1/libraries"
_LIBRARY_NAME = "Household Movies"
_LIBRARY_PATH = "/mnt/homeflix-secret-root/movies"


@pytest.fixture
async def library_id(session_factory: async_sessionmaker[AsyncSession]) -> str:
    """Seed one library with a single root path and return its id."""
    library = Library.create(
        name=_LIBRARY_NAME,
        library_type=LibraryType.MOVIES,
        paths=[_LIBRARY_PATH],
    )
    async with SqlAlchemyLibraryUnitOfWorkFactory(session_factory)() as uow:
        saved = await uow.libraries.save(library)
    return str(saved.id)


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
class TestListLibrariesAuth:
    """Any signed-in user may list; only an admin sees the paths."""

    async def test_anonymous_caller_gets_401_without_the_path(
        self, client: AsyncClient, library_id: str
    ) -> None:
        response = await client.get(LIBRARIES_PATH)

        assert response.status_code == 401
        assert _LIBRARY_PATH not in response.text

    async def test_member_gets_the_list_with_paths_emptied(
        self,
        client: AsyncClient,
        library_id: str,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login(client, seed_user_with_profile, is_admin=False)

        response = await client.get(LIBRARIES_PATH)

        assert response.status_code == 200
        [library] = response.json()["data"]
        assert library["id"] == library_id
        assert library["name"] == _LIBRARY_NAME
        assert library["paths"] == []
        assert _LIBRARY_PATH not in response.text

    async def test_admin_gets_the_list_with_paths(
        self,
        client: AsyncClient,
        library_id: str,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login(client, seed_user_with_profile, is_admin=True)

        response = await client.get(LIBRARIES_PATH)

        assert response.status_code == 200
        [library] = response.json()["data"]
        assert library["id"] == library_id
        assert library["name"] == _LIBRARY_NAME
        assert library["paths"] == [_LIBRARY_PATH]


@pytest.mark.e2e
class TestGetLibraryAuth:
    """The single-library read is admin-only."""

    async def test_anonymous_caller_gets_401_without_the_path(
        self, client: AsyncClient, library_id: str
    ) -> None:
        response = await client.get(f"{LIBRARIES_PATH}/{library_id}")

        assert response.status_code == 401
        assert _LIBRARY_PATH not in response.text

    async def test_member_gets_403_without_the_path(
        self,
        client: AsyncClient,
        library_id: str,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login(client, seed_user_with_profile, is_admin=False)

        response = await client.get(f"{LIBRARIES_PATH}/{library_id}")

        assert response.status_code == 403
        assert _LIBRARY_PATH not in response.text

    async def test_admin_gets_the_library_with_paths(
        self,
        client: AsyncClient,
        library_id: str,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login(client, seed_user_with_profile, is_admin=True)

        response = await client.get(f"{LIBRARIES_PATH}/{library_id}")

        assert response.status_code == 200
        library = response.json()["data"]
        assert library["id"] == library_id
        assert library["name"] == _LIBRARY_NAME
        assert library["paths"] == [_LIBRARY_PATH]
