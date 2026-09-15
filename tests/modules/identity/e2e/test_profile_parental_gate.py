"""End-to-end tests for the parental gate on the profile routes (ADR-035, Amendment 7).

Drives switch, ``PUT``, ``POST`` and ``DELETE /api/v1/profiles`` through the
real app for accounts with a parental PIN, following the "decision 9 per
operation" table: what needs an unlock, that the operation spends it (D9),
that widening a profile drops the other devices on it (D12), that a limit
never exists without a PIN (D2), and that the gate answers 403 or 409, never
401.

The PIN and the unlock go through their real routes. Profiles an account
starts with are written straight to the database, so each test begins from
the household it describes.
"""

import json
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config.settings import get_settings
from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import ProfileModel
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import SQLAlchemyMovieRepository
from src.shared_kernel.value_objects import AgeRating, Certification, ContentRating, RatingSystem
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.identity.e2e.conftest import SeededUser

pytestmark = pytest.mark.e2e

LOGIN_PATH = "/api/v1/auth/cookie/login"
PIN_PATH = "/api/v1/parental/pin"
UNLOCK_PATH = "/api/v1/parental/unlock"
PROFILES_PATH = "/api/v1/profiles"
ADMIN_USERS_PATH = "/api/v1/admin/users"

_PIN = "904518"
_LIBRARY = "lib_gatelibrary1"

Factory = async_sessionmaker[AsyncSession]


# ─── helpers ───────────────────────────────────────────────


async def _login(client: AsyncClient, user: SeededUser) -> str:
    response = await client.post(
        LOGIN_PATH, data={"username": user.email, "password": user.password}
    )
    assert response.status_code == 204
    token = client.cookies.get(get_settings().session_cookie_name)
    assert token is not None
    return token


async def _set_pin(client: AsyncClient, user: SeededUser) -> None:
    response = await client.put(PIN_PATH, json={"current_password": user.password, "pin": _PIN})
    assert response.status_code == 204, response.text


async def _unlock(client: AsyncClient) -> None:
    response = await client.post(UNLOCK_PATH, json={"pin": _PIN})
    assert response.status_code == 204, response.text


def _switch(client: AsyncClient, profile_id: str) -> Awaitable[Response]:
    return client.post(f"{PROFILES_PATH}/{profile_id}/switch")


def _put(client: AsyncClient, profile_id: str, body: dict[str, Any]) -> Awaitable[Response]:
    return client.put(f"{PROFILES_PATH}/{profile_id}", json=body)


async def _add_profile(
    session_factory: Factory,
    user: SeededUser,
    name: str,
    limit: int | None,
    *,
    libraries: list[str] | None = None,
) -> str:
    profile_id = ProfileId.generate().value
    async with session_factory() as session:
        user_uuid = await session.scalar(
            select(UserModel.id).where(UserModel.external_id == user.user_external_id)
        )
        session.add(
            ProfileModel(
                external_id=profile_id,
                user_id=user_uuid,
                name=name,
                is_kids=limit is not None and limit <= 12,
                maturity_limit=limit,
                allowed_library_ids=json.dumps(libraries or []),
            )
        )
        await session.commit()
    return profile_id


async def _set_profile(session_factory: Factory, profile_id: str, **values: Any) -> None:
    async with session_factory() as session:
        await session.execute(
            update(ProfileModel).where(ProfileModel.external_id == profile_id).values(**values)
        )
        await session.commit()


async def _limit(session_factory: Factory, profile_id: str) -> int | None:
    async with session_factory() as session:
        return await session.scalar(
            select(ProfileModel.maturity_limit).where(ProfileModel.external_id == profile_id)
        )


async def _is_live(session_factory: Factory, profile_id: str) -> bool:
    async with session_factory() as session:
        deleted_at = await session.scalar(
            select(ProfileModel.deleted_at).where(ProfileModel.external_id == profile_id)
        )
    return deleted_at is None


async def _active_profile(session_factory: Factory, token: str) -> str | None:
    async with session_factory() as session:
        return await session.scalar(
            select(ProfileModel.external_id)
            .join(AccessTokenModel, AccessTokenModel.current_profile_id == ProfileModel.id)
            .where(AccessTokenModel.token == token)
        )


async def _user_count(session_factory: Factory) -> int:
    async with session_factory() as session:
        return int((await session.execute(select(func.count(UserModel.id)))).scalar_one())


def _assert_pin_required(response: Response) -> None:
    body = response.json() if response.content else {}
    assert (response.status_code, body.get("code")) == (403, "PARENTAL_PIN_REQUIRED")


@contextmanager
def _count_queries(session_factory: Factory) -> Iterator[list[str]]:
    engine = session_factory.kw["bind"].sync_engine
    statements: list[str] = []

    def _record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _record)


@pytest.fixture
async def parent(
    client: AsyncClient,
    seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
) -> AsyncIterator[SeededUser]:
    """A logged-in administrator with a parental PIN; its seeded profile is unrestricted."""
    user = await seed_user_with_profile(email="parent@example.com", is_admin=True)
    await _login(client, user)
    await _set_pin(client, user)
    yield user


@pytest.fixture
async def kid(session_factory: Factory, parent: SeededUser) -> str:
    """A live profile of the parent's account, limited to 12."""
    return await _add_profile(session_factory, parent, "Kid", 12, libraries=[_LIBRARY])


@pytest.fixture
async def tablet(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """A second device: its own client, so its own session cookie."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


@pytest.fixture
async def phone(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """A third device."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


# ─── switch ────────────────────────────────────────────────


class TestSwitch:
    async def test_every_switch_closes_the_window(
        self, client: AsyncClient, parent: SeededUser, kid: str
    ) -> None:
        # D9: the parent unlocks on their own profile and hands the device
        # over on the kid's; that switch needs no unlock, yet it closes the
        # window, so nothing is left to return to the parent with.
        await _unlock(client)
        to_parent = await _switch(client, parent.profile_external_id)
        await _unlock(client)

        to_kid = await _switch(client, kid)
        back_to_parent = await _switch(client, parent.profile_external_id)

        assert (to_parent.status_code, to_kid.status_code) == (204, 204)
        _assert_pin_required(back_to_parent)

    async def test_a_new_session_enters_the_lowest_limit_but_not_the_unrestricted_profile(
        self,
        client: AsyncClient,
        session_factory: Factory,
        parent: SeededUser,
        kid: str,
    ) -> None:
        # D1: right after login no profile is selected.
        token = client.cookies.get(get_settings().session_cookie_name)
        assert token is not None

        _assert_pin_required(await _switch(client, parent.profile_external_id))
        assert await _active_profile(session_factory, token) is None
        assert (await _switch(client, kid)).status_code == 204

    async def test_a_session_on_a_deleted_profile_cannot_enter_a_limited_one(
        self,
        client: AsyncClient,
        session_factory: Factory,
        parent: SeededUser,
    ) -> None:
        # Read as "no profile selected", the session would get the lowest live
        # limit, 10, and enter the 10 freely.
        gone = await _add_profile(session_factory, parent, "Gone", None)
        assert (await _switch(client, gone)).status_code == 204
        ten = await _add_profile(session_factory, parent, "Ten", 10)
        await _set_profile(session_factory, gone, deleted_at=func.current_timestamp())

        _assert_pin_required(await _switch(client, ten))

    async def test_ownership_answers_before_the_gate(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        parent: SeededUser,
        kid: str,
    ) -> None:
        stranger = await seed_user_with_profile(email="stranger@example.com")
        assert (await _switch(client, kid)).status_code == 204

        response = await _switch(client, stranger.profile_external_id)

        assert (response.status_code, response.json()["code"]) == (
            403,
            "PROFILE_OWNERSHIP_VIOLATION",
        )


# ─── update ────────────────────────────────────────────────


class TestUpdate:
    @pytest.fixture(autouse=True)
    async def _on_the_kid(self, client: AsyncClient, kid: str) -> None:
        assert (await _switch(client, kid)).status_code == 204

    async def test_the_whole_form_with_a_new_name_passes_without_an_unlock(
        self, client: AsyncClient, session_factory: Factory, kid: str
    ) -> None:
        # The web client sends name, is_kids and the libraries on every submit.
        response = await _put(
            client,
            kid,
            {"name": "Renamed", "is_kids": False, "allowed_library_ids": [_LIBRARY]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["data"]["maturity_limit"] == 12
        assert await _limit(session_factory, kid) == 12

    async def test_a_wider_library_list_with_the_same_limit_passes(
        self, client: AsyncClient, kid: str
    ) -> None:
        # D5: the ACL is not gated.
        response = await _put(client, kid, {"allowed_library_ids": [_LIBRARY, "lib_otherlibrary"]})

        assert response.status_code == 200, response.text

    @pytest.mark.parametrize("wider", [14, None])
    async def test_widening_is_refused_until_an_unlock(
        self, client: AsyncClient, session_factory: Factory, kid: str, wider: int | None
    ) -> None:
        _assert_pin_required(await _put(client, kid, {"maturity_limit": wider}))
        assert await _limit(session_factory, kid) == 12

        await _unlock(client)
        response = await _put(client, kid, {"maturity_limit": wider})

        assert response.status_code == 200, response.text
        assert await _limit(session_factory, kid) == wider

    async def test_narrowing_the_active_profile_passes(
        self, client: AsyncClient, session_factory: Factory, kid: str
    ) -> None:
        response = await _put(client, kid, {"maturity_limit": 10})

        assert response.status_code == 200, response.text
        assert await _limit(session_factory, kid) == 10

    async def test_narrowing_another_profile_needs_an_unlock_only_from_a_limited_session(
        self,
        client: AsyncClient,
        session_factory: Factory,
        parent: SeededUser,
        kid: str,
    ) -> None:
        teen = await _add_profile(session_factory, parent, "Teen", 14)

        _assert_pin_required(await _put(client, teen, {"maturity_limit": 12}))
        assert await _limit(session_factory, teen) == 14

        await _unlock(client)
        assert (await _switch(client, parent.profile_external_id)).status_code == 204
        response = await _put(client, teen, {"maturity_limit": 12})

        assert response.status_code == 200, response.text
        assert await _limit(session_factory, teen) == 12

    async def test_one_unlock_pays_for_one_widening(
        self,
        client: AsyncClient,
        session_factory: Factory,
        parent: SeededUser,
    ) -> None:
        a = await _add_profile(session_factory, parent, "A", 10)
        b = await _add_profile(session_factory, parent, "B", 10)
        await _unlock(client)

        first = await _put(client, a, {"maturity_limit": None})
        second = await _put(client, b, {"maturity_limit": None})

        assert first.status_code == 200, first.text
        _assert_pin_required(second)
        assert (await _limit(session_factory, a), await _limit(session_factory, b)) == (None, 10)

    async def test_an_omitted_limit_is_kept_and_a_null_one_removes_it(
        self, client: AsyncClient, session_factory: Factory, kid: str
    ) -> None:
        omitted = await _put(client, kid, {"name": "Still limited"})
        await _unlock(client)
        removed = await _put(client, kid, {"maturity_limit": None})

        assert omitted.json()["data"]["maturity_limit"] == 12
        assert removed.json()["data"]["maturity_limit"] is None
        assert await _limit(session_factory, kid) is None

    @pytest.mark.parametrize("value", [True, "12", 12.5, 12.0, 22, -1])
    async def test_a_limit_that_is_not_a_whole_age_is_422(
        self, client: AsyncClient, session_factory: Factory, kid: str, value: object
    ) -> None:
        put = await _put(client, kid, {"maturity_limit": value})
        post = await client.post(PROFILES_PATH, json={"name": "New", "maturity_limit": value})

        assert (put.status_code, post.status_code) == (422, 422)
        # Refused by the schema, not later by ``AgeRating``: for 22 and -1 the
        # value object would also answer 422, with another code.
        assert (put.json()["code"], post.json()["code"]) == (
            "REQUEST_VALIDATION_ERROR",
            "REQUEST_VALIDATION_ERROR",
        )
        assert await _limit(session_factory, kid) == 12


# ─── widening drops the other devices ──────────────────────


class TestWideningDetachesTheOtherDevices:
    async def test_the_tablet_on_a_widened_profile_is_dropped_and_the_tv_stays(
        self,
        client: AsyncClient,
        tablet: AsyncClient,
        phone: AsyncClient,
        session_factory: Factory,
        parent: SeededUser,
    ) -> None:
        tv = client
        tv_token = tv.cookies.get(get_settings().session_cookie_name)
        assert tv_token is not None
        k = await _add_profile(session_factory, parent, "K", 10)
        movie_16 = await _seed_movie(session_factory, age=16)
        statuses: list[int] = []

        # The TV is on the parent; the tablet and the phone on K (10).
        await _unlock(tv)
        statuses.append((await _switch(tv, parent.profile_external_id)).status_code)
        tablet_token = await _login(tablet, parent)
        statuses.append((await _switch(tablet, k)).status_code)
        phone_token = await _login(phone, parent)
        statuses.append((await _switch(phone, k)).status_code)

        # On the TV, the parent's profile is narrowed to 10: it is the active
        # one, so no unlock. The tablet then enters it: 10 does not exceed 10.
        statuses.append(
            (await _put(tv, parent.profile_external_id, {"maturity_limit": 10})).status_code
        )
        statuses.append((await _switch(tablet, parent.profile_external_id)).status_code)
        assert await _active_profile(session_factory, tablet_token) == parent.profile_external_id

        # The parent notices, unlocks the TV and removes the limit.
        await _unlock(tv)
        widened = await _put(tv, parent.profile_external_id, {"maturity_limit": None})
        statuses.append(widened.status_code)

        assert statuses == [204, 204, 204, 200, 204, 200]
        assert await _active_profile(session_factory, tablet_token) is None
        assert await _active_profile(session_factory, tv_token) == parent.profile_external_id
        assert await _active_profile(session_factory, phone_token) == k

        # D12: the detached tablet falls back to the existing 401 of the
        # catalog, and its admin authority is suspended (no profile selected
        # counts as the lowest live limit, 10).
        before = await _user_count(session_factory)
        detail = await tablet.get(f"/api/v1/movies/{movie_16}")
        admin = await tablet.post(
            ADMIN_USERS_PATH,
            json={"email": "new@example.com", "password": "initial-password", "role": "member"},
        )

        assert detail.status_code == 401
        _assert_pin_required(admin)
        assert await _user_count(session_factory) == before


# ─── create ────────────────────────────────────────────────


class TestCreate:
    async def test_an_unrestricted_profile_needs_an_unlock_from_a_limited_session(
        self,
        client: AsyncClient,
        parent: SeededUser,
        kid: str,
    ) -> None:
        assert (await _switch(client, kid)).status_code == 204
        listed = len((await client.get(PROFILES_PATH)).json()["data"])

        refused = await client.post(PROFILES_PATH, json={"name": "Free", "maturity_limit": None})
        within = await client.post(PROFILES_PATH, json={"name": "Ten", "maturity_limit": 10})

        _assert_pin_required(refused)
        assert within.status_code == 201, within.text
        assert len((await client.get(PROFILES_PATH)).json()["data"]) == listed + 1

    async def test_an_unrestricted_session_creates_an_unrestricted_profile(
        self,
        client: AsyncClient,
        parent: SeededUser,
        kid: str,
    ) -> None:
        await _unlock(client)
        assert (await _switch(client, parent.profile_external_id)).status_code == 204

        response = await client.post(PROFILES_PATH, json={"name": "Free", "maturity_limit": None})

        assert response.status_code == 201, response.text


# ─── delete ────────────────────────────────────────────────


class TestDelete:
    async def test_deleting_a_limited_profile_needs_an_unlock(
        self,
        client: AsyncClient,
        session_factory: Factory,
        parent: SeededUser,
        kid: str,
    ) -> None:
        await _unlock(client)
        assert (await _switch(client, parent.profile_external_id)).status_code == 204

        refused = await client.delete(f"{PROFILES_PATH}/{kid}")
        assert await _is_live(session_factory, kid)
        await _unlock(client)
        deleted = await client.delete(f"{PROFILES_PATH}/{kid}")

        _assert_pin_required(refused)
        assert deleted.status_code == 204
        assert not await _is_live(session_factory, kid)

    async def test_the_last_profile_answers_409_before_the_gate(
        self,
        client: AsyncClient,
        session_factory: Factory,
        parent: SeededUser,
    ) -> None:
        await _set_profile(session_factory, parent.profile_external_id, maturity_limit=12)

        response = await client.delete(f"{PROFILES_PATH}/{parent.profile_external_id}")

        assert (response.status_code, response.json()["code"]) == (
            409,
            "CANNOT_DELETE_LAST_PROFILE",
        )


# ─── the PIN invariant ─────────────────────────────────────


class TestLimitsNeedAPin:
    async def test_the_pin_cannot_be_removed_while_a_profile_is_limited(
        self,
        client: AsyncClient,
        parent: SeededUser,
        kid: str,
    ) -> None:
        body = {"current_password": parent.password}

        in_use = await client.post(f"{PIN_PATH}/remove", json=body)
        await _unlock(client)
        assert (await _put(client, kid, {"maturity_limit": None})).status_code == 200
        removed = await client.post(f"{PIN_PATH}/remove", json=body)

        assert (in_use.status_code, in_use.json()["code"]) == (409, "PARENTAL_PIN_IN_USE")
        assert removed.status_code == 204

    async def test_an_account_without_a_pin_writes_no_limit(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile(email="nopin@example.com")
        await _login(client, user)

        post = await client.post(PROFILES_PATH, json={"name": "Kid", "maturity_limit": 12})
        put = await _put(client, user.profile_external_id, {"maturity_limit": 12})
        rename = await _put(client, user.profile_external_id, {"name": "Renamed"})

        assert [(r.status_code, r.json()["code"]) for r in (post, put)] == [
            (409, "PARENTAL_PIN_NOT_CONFIGURED")
        ] * 2
        assert rename.status_code == 200


# ─── never 401, and the cost ───────────────────────────────


class TestNever401:
    async def test_every_gate_refusal_is_403(
        self,
        client: AsyncClient,
        session_factory: Factory,
        parent: SeededUser,
        kid: str,
    ) -> None:
        assert (await _switch(client, kid)).status_code == 204
        teen = await _add_profile(session_factory, parent, "Teen", 14)

        refusals = [
            await _switch(client, parent.profile_external_id),
            await _put(client, kid, {"maturity_limit": None}),
            await _put(client, teen, {"maturity_limit": 12}),
            await client.post(PROFILES_PATH, json={"name": "Free"}),
            await client.delete(f"{PROFILES_PATH}/{teen}"),
        ]

        assert [(r.status_code, r.json()["code"]) for r in refusals] == [
            (403, "PARENTAL_PIN_REQUIRED")
        ] * 5


class TestQueryCost:
    async def test_a_pin_adds_exactly_two_queries_to_a_rename_and_a_switch(
        self,
        client: AsyncClient,
        session_factory: Factory,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        # Without a PIN the gate reads the account only; with one it also
        # reads the session's parental state and the account's profiles.
        user = await seed_user_with_profile(email="cost@example.com")
        await _login(client, user)
        profile = user.profile_external_id

        async def measure() -> tuple[int, int]:
            assert (await _put(client, profile, {"name": "Same"})).status_code == 200  # warm-up
            with _count_queries(session_factory) as renames:
                assert (await _put(client, profile, {"name": "Same"})).status_code == 200
            with _count_queries(session_factory) as switches:
                assert (await _switch(client, profile)).status_code == 204
            return len(renames), len(switches)

        without_pin = await measure()
        await _set_pin(client, user)
        with_pin = await measure()

        assert (with_pin[0] - without_pin[0], with_pin[1] - without_pin[1]) == (2, 2)


async def _seed_movie(session_factory: Factory, *, age: int) -> str:
    movie = Movie(
        library_id=_LIBRARY,
        id=MovieId.generate(),
        title=Title(f"Rated {age}"),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(f"/movies/rated-{age}.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
        certification=Certification(
            system=RatingSystem.BR_DEJUS,
            label=ContentRating(str(age)),
            minimum_age=AgeRating(age),
        ),
    )
    async with session_factory() as session:
        saved = await SQLAlchemyMovieRepository(session).save(movie)
        await session.commit()
    return str(saved.id)
