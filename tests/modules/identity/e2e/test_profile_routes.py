"""End-to-end tests for the profile routes.

Drives ``/api/v1/profiles`` (CRUD + switch) over the same in-process
ASGI transport set up in ``conftest.py``. Covers the happy path,
ownership isolation between distinct users, the can't-delete-last
invariant, and the session-row update on profile switch.
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
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
PIN_PATH = "/api/v1/parental/pin"


async def _login(client: AsyncClient, user: SeededUser) -> None:
    response = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert response.status_code == 204


async def _set_pin(client: AsyncClient, user: SeededUser) -> None:
    response = await client.put(PIN_PATH, json={"current_password": user.password, "pin": "904518"})
    assert response.status_code == 204, response.text


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


async def _stored_limit_and_flag(
    session_factory: async_sessionmaker[AsyncSession],
    external_id: str,
) -> tuple[int | None, bool]:
    """Return the stored ``(maturity_limit, is_kids)`` of a profile row."""
    async with session_factory() as session:
        result = await session.execute(
            select(ProfileModel.maturity_limit, ProfileModel.is_kids).where(
                ProfileModel.external_id == external_id
            )
        )
        limit, is_kids = result.one()
        return limit, is_kids


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

    async def test_should_return_the_profile_contract_keys(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        # The web client reads this payload; the shape only grows on
        # purpose. ``maturity_limit`` joined it with ADR-035, and
        # ``is_kids`` stays as a derived field.
        user = await seed_user_with_profile()
        await _login(client, user)

        items = (await client.get(PROFILES_PATH)).json()["data"]

        assert [set(item) for item in items] == [
            {
                "id",
                "user_id",
                "name",
                "avatar_url",
                "is_kids",
                "maturity_limit",
                "allowed_library_ids",
                "created_at",
                "updated_at",
            }
        ]
        assert items[0]["maturity_limit"] is None
        assert items[0]["is_kids"] is False

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
            json={"name": "Kids"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["type"] == "profile"
        created = body["data"]
        assert created["id"].startswith("prf_")
        assert created["user_id"] == user.user_external_id
        assert created["name"] == "Kids"

        # Listing now returns 2 profiles for this user.
        listing = (await client.get(PROFILES_PATH)).json()["data"]
        assert len(listing) == 2

    async def test_should_accept_and_ignore_a_kids_flag(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ):
        # ``is_kids`` is derived from the maturity limit now (ADR-035);
        # the web client still sends it, so it must not be a 422.
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.post(PROFILES_PATH, json={"name": "Kids", "is_kids": True})

        assert response.status_code == 201
        created = response.json()["data"]
        assert created["is_kids"] is False
        assert created["maturity_limit"] is None
        assert await _stored_limit_and_flag(session_factory, created["id"]) == (None, False)

    @pytest.mark.parametrize(("limit", "is_kids"), [(12, True), (21, False)])
    async def test_should_store_a_maturity_limit_on_an_account_with_a_pin(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
        limit: int,
        is_kids: bool,
    ):
        # The session acts under no limit (the account has none yet), so a
        # limited profile needs no unlock (ADR-035, Amendment 7).
        user = await seed_user_with_profile()
        await _login(client, user)
        await _set_pin(client, user)

        response = await client.post(PROFILES_PATH, json={"name": "Kids", "maturity_limit": limit})

        assert response.status_code == 201, response.text
        created = response.json()["data"]
        assert (created["maturity_limit"], created["is_kids"]) == (limit, is_kids)
        assert await _stored_limit_and_flag(session_factory, created["id"]) == (limit, is_kids)

    @pytest.mark.parametrize("limit", [12, 21])
    async def test_should_refuse_a_maturity_limit_without_a_pin(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        limit: int,
    ):
        # Amendment 7 D2: a limit without a PIN would protect nothing.
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.post(PROFILES_PATH, json={"name": "Kids", "maturity_limit": limit})

        assert (response.status_code, response.json()["code"]) == (
            409,
            "PARENTAL_PIN_NOT_CONFIGURED",
        )
        assert len((await client.get(PROFILES_PATH)).json()["data"]) == 1

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

    async def test_should_default_allowed_library_ids_to_empty_when_omitted(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        # Default-deny: a fresh profile that does not name any
        # libraries explicitly comes back with an empty ACL.
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.post(PROFILES_PATH, json={"name": "Anon"})

        assert response.status_code == 201
        assert response.json()["data"]["allowed_library_ids"] == []

    async def test_should_persist_allowed_library_ids_when_supplied(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.post(
            PROFILES_PATH,
            json={
                "name": "Lucas",
                "allowed_library_ids": ["lib_movies123456", "lib_series123456"],
            },
        )

        assert response.status_code == 201
        created = response.json()["data"]
        assert created["allowed_library_ids"] == ["lib_movies123456", "lib_series123456"]


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
        assert updated["maturity_limit"] is None

    async def test_should_accept_and_ignore_a_kids_flag(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ):
        user = await seed_user_with_profile(profile_name="Old")
        await _login(client, user)

        response = await client.put(
            f"{PROFILES_PATH}/{user.profile_external_id}",
            json={"name": "Kid", "is_kids": True},
        )

        assert response.status_code == 200
        updated = response.json()["data"]
        assert updated["name"] == "Kid"
        assert updated["is_kids"] is False
        assert updated["maturity_limit"] is None
        assert await _stored_limit_and_flag(session_factory, user.profile_external_id) == (
            None,
            False,
        )

    @pytest.mark.parametrize(("limit", "is_kids"), [(10, True), (21, False)])
    async def test_should_store_a_maturity_limit_on_an_account_with_a_pin(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
        limit: int,
        is_kids: bool,
    ):
        # Limiting an unrestricted profile narrows it: no unlock is needed.
        user = await seed_user_with_profile()
        await _login(client, user)
        await _set_pin(client, user)

        response = await client.put(
            f"{PROFILES_PATH}/{user.profile_external_id}",
            json={"maturity_limit": limit},
        )

        assert response.status_code == 200, response.text
        updated = response.json()["data"]
        assert (updated["maturity_limit"], updated["is_kids"]) == (limit, is_kids)
        assert await _stored_limit_and_flag(session_factory, user.profile_external_id) == (
            limit,
            is_kids,
        )

    @pytest.mark.parametrize("limit", [10, 21])
    async def test_should_refuse_a_maturity_limit_without_a_pin(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
        limit: int,
    ):
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.put(
            f"{PROFILES_PATH}/{user.profile_external_id}",
            json={"maturity_limit": limit},
        )

        assert (response.status_code, response.json()["code"]) == (
            409,
            "PARENTAL_PIN_NOT_CONFIGURED",
        )
        assert await _stored_limit_and_flag(session_factory, user.profile_external_id) == (
            None,
            False,
        )

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

    async def test_should_replace_allowed_library_ids_when_supplied(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        user = await seed_user_with_profile()
        await _login(client, user)

        response = await client.put(
            f"{PROFILES_PATH}/{user.profile_external_id}",
            json={"allowed_library_ids": ["lib_grant1235678"]},
        )

        assert response.status_code == 200
        assert response.json()["data"]["allowed_library_ids"] == ["lib_grant1235678"]

    async def test_should_revoke_all_libraries_with_explicit_empty_list(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        # Empty list is meaningful: revoke every library. Distinct
        # from "field omitted" (None), which leaves the ACL alone.
        user = await seed_user_with_profile()
        await _login(client, user)
        await client.put(
            f"{PROFILES_PATH}/{user.profile_external_id}",
            json={"allowed_library_ids": ["lib_grant1235678"]},
        )

        response = await client.put(
            f"{PROFILES_PATH}/{user.profile_external_id}",
            json={"allowed_library_ids": []},
        )

        assert response.status_code == 200
        assert response.json()["data"]["allowed_library_ids"] == []

    async def test_should_leave_allowed_library_ids_alone_when_omitted(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ):
        # PATCH-style semantics: omitted field never touches the
        # underlying value, even when other fields are updated.
        user = await seed_user_with_profile()
        await _login(client, user)
        await client.put(
            f"{PROFILES_PATH}/{user.profile_external_id}",
            json={"allowed_library_ids": ["lib_keepvalue123"]},
        )

        response = await client.put(
            f"{PROFILES_PATH}/{user.profile_external_id}",
            json={"name": "Renamed"},
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["name"] == "Renamed"
        assert body["allowed_library_ids"] == ["lib_keepvalue123"]


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
