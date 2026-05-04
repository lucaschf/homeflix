"""End-to-end tests for the profile routes.

Drives ``/api/v1/profiles`` (CRUD + switch) over the same in-process
ASGI transport set up in ``conftest.py``. Covers the happy path,
ownership isolation between distinct users, the can't-delete-last
invariant, and the session-row update on profile switch.
"""

import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.identity.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
PROFILES_PATH = "/api/v1/profiles"


async def _login(client: AsyncClient, user: SeededUser) -> None:
    response = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert response.status_code == 204


async def _get_active_profile_uuid(
    session_factory: async_sessionmaker[AsyncSession],
) -> uuid.UUID | None:
    """Return ``access_tokens.current_profile_id`` for the seeded session."""
    async with session_factory() as session:
        result = await session.execute(select(AccessTokenModel.current_profile_id))
        return result.scalar_one_or_none()


async def _profile_uuid_for_external(
    session_factory: async_sessionmaker[AsyncSession],
    external_id: str,
) -> uuid.UUID | None:
    """Resolve a prefixed ``ProfileId`` to the matching internal UUID."""
    async with session_factory() as session:
        result = await session.execute(
            select(ProfileModel.id).where(ProfileModel.external_id == external_id)
        )
        return result.scalar_one_or_none()


class TestListProfiles:
    async def test_should_return_owned_profiles_with_prefixed_ids(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile(profile_name="Lucas")
        await _login(client, user)

        response = await client.get(PROFILES_PATH)

        assert response.status_code == 200
        body = response.json()
        items = body["data"]
        assert len(items) == 1
        assert items[0]["id"] == user.profile_external_id
        assert items[0]["id"].startswith("prf_")
        assert items[0]["name"] == "Lucas"
        assert items[0]["user_id"] == user.user_external_id

    async def test_should_return_401_when_unauthenticated(self, client: AsyncClient):
        response = await client.get(PROFILES_PATH)
        assert response.status_code == 401


class TestCreateProfile:
    async def test_should_return_201_and_persist_profile_owned_by_caller(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.post(
            PROFILES_PATH,
            json={"name": "Kids", "is_kids": True},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["type"] == "profile"
        created = body["data"]
        assert created["id"].startswith("prf_")
        assert created["user_id"] == user.user_external_id
        assert created["name"] == "Kids"
        assert created["is_kids"] is True

        # Listing now returns 2 profiles for this user.
        listing = (await client.get(PROFILES_PATH)).json()["data"]
        assert len(listing) == 2

    async def test_should_reject_blank_name(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.post(PROFILES_PATH, json={"name": ""})

        # Pydantic schema rejects empty name (min_length=1) -> 422.
        assert response.status_code == 422


class TestUpdateProfile:
    async def test_should_apply_partial_update(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile(profile_name="Old")
        await _login(client, user)

        response = await client.put(
            f"{PROFILES_PATH}/{user.profile_external_id}",
            json={"name": "New"},
        )

        assert response.status_code == 200
        updated = response.json()["data"]
        assert updated["id"] == user.profile_external_id
        assert updated["name"] == "New"
        # is_kids unchanged because it was not supplied
        assert updated["is_kids"] is False

    async def test_should_return_404_when_profile_does_not_exist(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()
        await _login(client, user)
        # Generate a syntactically valid prefixed ID that is guaranteed
        # not to collide with any seeded row (12 chars of random base62).
        unknown_id = ProfileId.generate().value

        response = await client.put(
            f"{PROFILES_PATH}/{unknown_id}",
            json={"name": "Whatever"},
        )
        assert response.status_code == 404


class TestDeleteProfile:
    async def test_should_return_204_when_user_has_more_than_one_profile(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile(profile_name="Keep")
        await _login(client, user)
        # Create a second profile so deletion does not hit the last-profile guard.
        created = (await client.post(PROFILES_PATH, json={"name": "Doomed"})).json()["data"]

        response = await client.delete(f"{PROFILES_PATH}/{created['id']}")

        assert response.status_code == 204
        listing = (await client.get(PROFILES_PATH)).json()["data"]
        assert {p["name"] for p in listing} == {"Keep"}

    async def test_should_return_409_when_deleting_last_profile(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.delete(f"{PROFILES_PATH}/{user.profile_external_id}")

        # ``CannotDeleteLastProfileError`` -> HTTP 409 (Conflict).
        assert response.status_code == 409


class TestSwitchProfile:
    async def test_should_persist_current_profile_id_on_session_row(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()
        await _login(client, user)
        # Sanity: a fresh login row has no active profile yet.
        assert await _get_active_profile_uuid(session_factory) is None

        response = await client.post(f"{PROFILES_PATH}/{user.profile_external_id}/switch")

        assert response.status_code == 204
        active_uuid = await _get_active_profile_uuid(session_factory)
        expected_uuid = await _profile_uuid_for_external(session_factory, user.profile_external_id)
        assert active_uuid == expected_uuid

    async def test_should_return_404_when_target_profile_does_not_exist(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()
        await _login(client, user)
        unknown_id = ProfileId.generate().value

        response = await client.post(f"{PROFILES_PATH}/{unknown_id}/switch")
        assert response.status_code == 404


class TestProfileIsolation:
    async def test_list_should_not_include_other_users_profiles(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        # Two distinct users, each with one profile.
        alice = await seed_user_with_profile(email="alice@example.com", profile_name="Alice")
        bob = await seed_user_with_profile(email="bob@example.com", profile_name="Bob")

        # Log in as Alice and verify she only sees her own profile.
        await _login(client, alice)
        listing = (await client.get(PROFILES_PATH)).json()["data"]

        assert len(listing) == 1
        assert listing[0]["id"] == alice.profile_external_id
        assert listing[0]["id"] != bob.profile_external_id

    async def test_should_return_403_when_updating_another_users_profile(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        alice = await seed_user_with_profile(email="alice@example.com", profile_name="Alice")
        bob = await seed_user_with_profile(email="bob@example.com", profile_name="Bob")

        # Alice tries to rename Bob's profile.
        await _login(client, alice)
        response = await client.put(
            f"{PROFILES_PATH}/{bob.profile_external_id}",
            json={"name": "Hijacked"},
        )

        assert response.status_code == 403

    async def test_should_return_403_when_deleting_another_users_profile(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        alice = await seed_user_with_profile(email="alice@example.com", profile_name="Alice")
        bob = await seed_user_with_profile(email="bob@example.com", profile_name="Bob")

        await _login(client, alice)
        response = await client.delete(f"{PROFILES_PATH}/{bob.profile_external_id}")

        assert response.status_code == 403

    async def test_should_return_403_when_switching_to_another_users_profile(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        alice = await seed_user_with_profile(email="alice@example.com", profile_name="Alice")
        bob = await seed_user_with_profile(email="bob@example.com", profile_name="Bob")

        await _login(client, alice)
        response = await client.post(f"{PROFILES_PATH}/{bob.profile_external_id}/switch")

        assert response.status_code == 403
