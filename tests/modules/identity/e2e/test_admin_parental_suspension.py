"""End-to-end tests for the admin suspension under the parental gate (ADR-035).

Drives admin routes through the real app for an account with a parental PIN,
following the Amendment 7 matrix: admin authority follows the session's
selected profile, and admin writes also need an unlock while any live
profile of the account has a limit (D10). A suspension is 403
``PARENTAL_PIN_REQUIRED``, never 401, and the unlock window is read, not
spent (D9).

Limits are written straight to the database, so a test starts from the
account it needs without spending unlocks on the profile routes. The PIN goes
through its real route. Entering the unrestricted profile while a limited one
exists needs an unlock, which the switch spends (decision 9).
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
    TmdbId,
    Year,
)
from src.modules.media.infrastructure.persistence.models.movie import MovieModel
from src.modules.media.infrastructure.persistence.repositories import SQLAlchemyMovieRepository
from tests.modules.identity.e2e.conftest import SeededUser

pytestmark = pytest.mark.e2e

LOGIN_PATH = "/api/v1/auth/cookie/login"
ME_PATH = "/api/v1/users/me"
PIN_PATH = "/api/v1/parental/pin"
UNLOCK_PATH = "/api/v1/parental/unlock"
PROFILES_PATH = "/api/v1/profiles"
ADMIN_USERS_PATH = "/api/v1/admin/users"
ADMIN_CATALOG_REQUESTS_PATH = "/api/v1/admin/catalog-requests"
LIBRARIES_PATH = "/api/v1/libraries"
CONTENT_RATING_PATH = "/api/v1/admin/settings/content-rating"

_PIN = "904518"
_TMDB_ID = 27205

_LIBRARY_BODY = {
    "name": "Movies",
    "library_type": "movies",
    "paths": ["/tmp/movies"],
    "language": "en",
    "metadata_providers": [{"provider": "tmdb", "priority": 1, "enabled": True}],
    "scan_schedule": None,
    "settings": {
        "generate_thumbnails": True,
        "detect_intros": True,
        "auto_refresh_metadata": True,
    },
}


def _new_user_body(email: str) -> dict[str, str]:
    return {"email": email, "password": "initial-password", "role": "member"}


async def _login(client: AsyncClient, user: SeededUser) -> None:
    response = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert response.status_code == 204


async def _set_pin(client: AsyncClient, user: SeededUser) -> None:
    response = await client.put(PIN_PATH, json={"current_password": user.password, "pin": _PIN})
    assert response.status_code == 204, response.text


async def _unlock(client: AsyncClient) -> None:
    response = await client.post(UNLOCK_PATH, json={"pin": _PIN})
    assert response.status_code == 204, response.text


async def _switch(client: AsyncClient, profile_id: str) -> None:
    response = await client.post(f"{PROFILES_PATH}/{profile_id}/switch")
    assert response.status_code == 204, response.text


async def _add_profile(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    name: str,
    *,
    limit: int | None,
) -> str:
    created = await client.post(PROFILES_PATH, json={"name": name})
    assert created.status_code == 201, created.text
    profile_id: str = created.json()["data"]["id"]
    if limit is not None:
        async with session_factory() as session:
            await session.execute(
                update(ProfileModel)
                .where(ProfileModel.external_id == profile_id)
                .values(maturity_limit=limit)
            )
            await session.commit()
    return profile_id


async def _soft_delete_profile(
    session_factory: async_sessionmaker[AsyncSession], profile_id: str
) -> None:
    async with session_factory() as session:
        await session.execute(
            update(ProfileModel)
            .where(ProfileModel.external_id == profile_id)
            .values(deleted_at=func.current_timestamp())
        )
        await session.commit()


async def _user_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return int((await session.execute(select(func.count(UserModel.id)))).scalar_one())


def _assert_pin_required(response: Response) -> None:
    assert (response.status_code, response.json().get("code")) == (403, "PARENTAL_PIN_REQUIRED")


@contextmanager
def _count_queries(session_factory: async_sessionmaker[AsyncSession]) -> Iterator[list[str]]:
    """Record every statement the shared test engine sends while the block runs."""
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
async def admin(
    client: AsyncClient,
    seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
) -> AsyncIterator[SeededUser]:
    """A logged-in administrator whose account has a parental PIN."""
    user = await seed_user_with_profile(email="parent@example.com", is_admin=True)
    await _login(client, user)
    await _set_pin(client, user)
    yield user


@pytest.fixture
async def kid_profile(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    admin: SeededUser,
) -> str:
    """A second, live profile of the admin's account, limited to 12."""
    return await _add_profile(client, session_factory, "Kid", limit=12)


class TestUnderALimitedProfile:
    """The session sits on the limited profile: admin reads and writes are suspended."""

    @pytest.fixture(autouse=True)
    async def _on_the_kid(self, client: AsyncClient, kid_profile: str) -> None:
        await _switch(client, kid_profile)

    async def test_creating_a_user_is_pin_required_and_creates_nothing(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # ``POST /admin/users`` depends on ``current_admin_user`` directly.
        before = await _user_count(session_factory)

        response = await client.post(ADMIN_USERS_PATH, json=_new_user_body("new@example.com"))

        _assert_pin_required(response)
        assert await _user_count(session_factory) == before

    async def test_relinking_a_movie_is_pin_required_and_keeps_its_tmdb_id(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie = Movie(
            library_id="lib_suspension01",
            id=MovieId.generate(),
            title=Title("Inception"),
            year=Year(2010),
            duration=Duration(8880),
            tmdb_id=TmdbId(_TMDB_ID),
            files=[
                MediaFile(
                    file_path=FilePath("/movies/inception.mkv"),
                    file_size=1_000_000_000,
                    resolution=Resolution("1080p"),
                    is_primary=True,
                )
            ],
        )
        async with session_factory() as session:
            saved = await SQLAlchemyMovieRepository(session).save(movie)
            await session.commit()

        response = await client.post(
            f"/api/v1/admin/movies/{saved.id}/relink",
            json={"tmdb_id": 603, "media_type": "movie"},
        )

        _assert_pin_required(response)
        async with session_factory() as session:
            stored = await session.execute(
                select(MovieModel.tmdb_id).where(MovieModel.external_id == str(saved.id))
            )
            assert stored.scalar_one() == _TMDB_ID

    async def test_changing_the_rating_jurisdiction_is_pin_required(
        self, client: AsyncClient
    ) -> None:
        response = await client.patch(
            CONTENT_RATING_PATH,
            json={"jurisdictions": ["US"], "fallback": "strictest_available"},
        )

        _assert_pin_required(response)

    @pytest.mark.parametrize("path", [ADMIN_USERS_PATH, ADMIN_CATALOG_REQUESTS_PATH])
    async def test_admin_reads_are_suspended_too(self, client: AsyncClient, path: str) -> None:
        _assert_pin_required(await client.get(path))

    async def test_an_unlock_opens_admin_writes_for_the_window_without_spending_it(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _unlock(client)
        before = await _user_count(session_factory)

        library = await client.post(LIBRARIES_PATH, json=_LIBRARY_BODY)
        created = await client.post(ADMIN_USERS_PATH, json=_new_user_body("new@example.com"))
        listed = await client.get(ADMIN_USERS_PATH)

        assert library.status_code in (200, 201), library.text
        assert created.status_code == 201, created.text
        assert listed.status_code == 200
        assert await _user_count(session_factory) == before + 1


class TestUnderTheUnrestrictedProfileWithALimitedSibling:
    """Amendment 7 D10: reads stay free, writes need an unlock."""

    @pytest.fixture(autouse=True)
    async def _on_the_parent(
        self, client: AsyncClient, admin: SeededUser, kid_profile: str
    ) -> None:
        await _unlock(client)
        await _switch(client, admin.profile_external_id)

    async def test_reads_are_granted_and_writes_need_an_unlock(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        before = await _user_count(session_factory)

        listed = await client.get(ADMIN_USERS_PATH)
        refused = await client.post(ADMIN_USERS_PATH, json=_new_user_body("new@example.com"))

        assert listed.status_code == 200
        _assert_pin_required(refused)
        assert await _user_count(session_factory) == before

        await _unlock(client)
        created = await client.post(ADMIN_USERS_PATH, json=_new_user_body("new@example.com"))

        assert created.status_code == 201, created.text
        assert await _user_count(session_factory) == before + 1


class TestSessionsWithoutALiveProfile:
    async def test_no_profile_selected_is_suspended_while_a_profile_is_limited(
        self, client: AsyncClient, kid_profile: str
    ) -> None:
        # Right after login no profile is selected: it counts as the lowest
        # limit of the account (Amendment 7 D1).
        _assert_pin_required(await client.get(ADMIN_USERS_PATH))
        _assert_pin_required(await client.post(LIBRARIES_PATH, json=_LIBRARY_BODY))

    async def test_a_deleted_selected_profile_is_suspended_with_no_limit_on_the_account(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        admin: SeededUser,
    ) -> None:
        # Read as "no profile selected", an account without limits would be
        # granted; a soft-deleted profile counts as age 0 instead.
        extra = await _add_profile(client, session_factory, "Old", limit=None)
        await _switch(client, extra)
        await _soft_delete_profile(session_factory, extra)

        _assert_pin_required(await client.get(ADMIN_USERS_PATH))

        await _unlock(client)
        assert (await client.get(ADMIN_USERS_PATH)).status_code == 200

    async def test_an_account_with_a_pin_and_no_limits_keeps_admin_without_a_profile(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        admin: SeededUser,
    ) -> None:
        # Login without a switch, as every admin e2e suite does: requiring a
        # profile, or D10 without a limited profile, would refuse this.
        library = await client.post(LIBRARIES_PATH, json=_LIBRARY_BODY)
        created = await client.post(ADMIN_USERS_PATH, json=_new_user_body("new@example.com"))

        assert library.status_code in (200, 201), library.text
        assert created.status_code == 201, created.text


class TestLibraryPaths:
    async def test_a_suspended_admin_reads_libraries_without_paths(
        self,
        client: AsyncClient,
        admin: SeededUser,
        kid_profile: str,
    ) -> None:
        await _unlock(client)
        await _switch(client, admin.profile_external_id)
        await _unlock(client)
        library = await client.post(LIBRARIES_PATH, json=_LIBRARY_BODY)
        assert library.status_code in (200, 201), library.text
        granted = await client.get(LIBRARIES_PATH)

        await _switch(client, kid_profile)
        suspended = await client.get(LIBRARIES_PATH)

        assert [lib["paths"] for lib in granted.json()["data"]] == [["/tmp/movies"]]
        assert suspended.status_code == 200
        assert [lib["paths"] for lib in suspended.json()["data"]] == [[]]


class TestMeReportsAdminAccess:
    async def test_member_has_none(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com")
        await _login(client, member)
        await _set_pin(client, member)

        assert (await client.get(ME_PATH)).json()["data"]["admin_access"] == "none"

    async def test_admin_without_pin_is_granted(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile(email="admin@example.com", is_admin=True)
        await _login(client, user)

        assert (await client.get(ME_PATH)).json()["data"]["admin_access"] == "granted"

    async def test_admin_access_follows_the_session_profile(
        self,
        client: AsyncClient,
        admin: SeededUser,
        kid_profile: str,
    ) -> None:
        await _unlock(client)
        await _switch(client, admin.profile_external_id)
        on_parent = (await client.get(ME_PATH)).json()["data"]["admin_access"]
        await _switch(client, kid_profile)
        on_kid = (await client.get(ME_PATH)).json()["data"]["admin_access"]
        await _unlock(client)
        unlocked = (await client.get(ME_PATH)).json()["data"]["admin_access"]

        # ``/users/me`` reports read authority: D10 does not apply to it.
        assert (on_parent, on_kid, unlocked) == ("granted", "suspended", "granted")


class TestQueryCost:
    """Without a PIN the gate costs nothing; with one, exactly one query.

    The session and the account's live profiles come from a single snapshot,
    so a widening cannot commit between them.
    """

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param(ADMIN_CATALOG_REQUESTS_PATH, id="authenticated_admin"),
            pytest.param(ADMIN_USERS_PATH, id="current_admin_user"),
        ],
    )
    async def test_a_pin_adds_exactly_one_query_to_an_admin_request(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        path: str,
    ) -> None:
        user = await seed_user_with_profile(email="admin@example.com", is_admin=True)
        await _login(client, user)

        async def _measure() -> list[str]:
            assert (await client.get(path)).status_code == 200  # warm-up
            with _count_queries(session_factory) as statements:
                assert (await client.get(path)).status_code == 200
            return statements

        without_pin = await _measure()
        await _set_pin(client, user)
        with_pin = await _measure()

        assert len(with_pin) == len(without_pin) + 1, with_pin


class TestNever401:
    async def test_no_suspended_or_granted_admin_request_is_401(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        admin: SeededUser,
        kid_profile: str,
    ) -> None:
        statuses: list[int] = []
        requests = [
            ("GET", ADMIN_USERS_PATH, None),
            ("POST", ADMIN_USERS_PATH, _new_user_body("x@example.com")),
            ("POST", LIBRARIES_PATH, _LIBRARY_BODY),
            ("GET", LIBRARIES_PATH, None),
            ("GET", ME_PATH, None),
        ]
        for profile in (None, admin.profile_external_id, kid_profile):
            if profile == admin.profile_external_id:
                await _unlock(client)
            if profile is not None:
                await _switch(client, profile)
            for method, path, body in requests:
                statuses.append((await client.request(method, path, json=body)).status_code)

        assert 401 not in statuses
        assert 403 in statuses
