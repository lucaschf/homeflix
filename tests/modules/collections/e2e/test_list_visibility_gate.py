"""End-to-end tests for the viewing policy on collections list reads (ADR-035).

Drives the real watchlist and custom-list routes over the in-process
ASGI transport against an in-memory database.

Most tests that need the age axis override the collections container's
``profile_viewing_policy`` provider with a policy that carries a limit;
the same requests without the override go through the real adapter,
which also proves the composition root hands the container an Identity
UoW factory and that every list read is wired to the provider.
``TestListReadsWithProfileMaturityLimit`` seeds the limit on the
profile itself, so it reaches the reads through that real adapter.

Rows are seeded straight through the repositories, not the write
routes, so these reads do not depend on how the writes are gated.
"""

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.modules.collections.e2e.conftest import SeededUser

from src.modules.collections.application.ports import ProfileViewingPolicyPort
from src.modules.collections.domain.entities import CustomList, CustomListItem, WatchlistItem
from src.modules.collections.domain.value_objects import ListId
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyCustomListRepository,
    SQLAlchemyWatchlistRepository,
)
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
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import (
    AgeRating,
    Certification,
    ContentRating,
    MediaType,
    RatingSystem,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

WATCHLIST_PATH = "/api/v1/watchlist"
CUSTOM_LISTS_PATH = "/api/v1/custom-lists"

_LIBRARY_ID = "lib_listsgate001"
_OTHER_LIBRARY_ID = "lib_otherlib0001"
_LIMIT = 12

_TEN_TITLE = "Ten Plus Movie"
_SIXTEEN_TITLE = "Sixteen Plus Movie"
_OTHER_SHELF_TITLE = "Other Shelf Movie"

type _Login = Callable[..., Awaitable[SeededUser]]


class _FixedViewingPolicy(ProfileViewingPolicyPort):
    """Answer every profile with one policy."""

    def __init__(self, policy: ViewingPolicy) -> None:
        self._policy = policy

    async def find_for_profile(self, profile_id: ProfileId) -> ViewingPolicy:
        return self._policy


@contextmanager
def _maturity_limit(app: FastAPI) -> Iterator[None]:
    """Resolve every profile to the seeded library with a maturity limit of 12."""
    provider = app.state.container.collections.profile_viewing_policy
    provider.override(
        providers.Object(
            _FixedViewingPolicy(
                ViewingPolicy(
                    allowed_library_ids=[_LIBRARY_ID],
                    maturity_limit=AgeRating(_LIMIT),
                )
            )
        )
    )
    try:
        yield
    finally:
        provider.reset_last_overriding()


def _certification(age: int) -> Certification:
    return Certification(
        system=RatingSystem.BR_DEJUS,
        label=ContentRating(str(age)),
        minimum_age=AgeRating(age),
    )


async def _seed_movie(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    title: str,
    age: int,
    library_id: str = _LIBRARY_ID,
) -> str:
    movie = Movie(
        library_id=library_id,
        id=MovieId.generate(),
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(f"/{library_id}/{title}.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
        certification=_certification(age),
    )
    async with session_factory() as session:
        saved = await SQLAlchemyMovieRepository(session).save(movie)
        await session.commit()
    return str(saved.id)


async def _seed_catalog(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    """One title within the limit, one above it, one on another shelf."""
    return {
        _TEN_TITLE: await _seed_movie(session_factory, title=_TEN_TITLE, age=10),
        _SIXTEEN_TITLE: await _seed_movie(session_factory, title=_SIXTEEN_TITLE, age=16),
        _OTHER_SHELF_TITLE: await _seed_movie(
            session_factory, title=_OTHER_SHELF_TITLE, age=10, library_id=_OTHER_LIBRARY_ID
        ),
    }


async def _seed_watchlist(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    profile_id: str,
    media_id: str,
    added_at: datetime,
) -> None:
    async with session_factory() as session:
        await SQLAlchemyWatchlistRepository(session).add(
            WatchlistItem(
                id=ListId.generate(),
                profile_id=ProfileId(profile_id),
                media_id=media_id,
                media_type=MediaType.MOVIE,
                added_at=added_at,
            )
        )
        await session.commit()


async def _seed_list(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    owner_profile_id: str,
    media_ids: list[str],
    shared: bool = False,
) -> CustomList:
    """Seed a list holding ``media_ids`` at positions ``0..n-1``, count in sync."""
    owner = ProfileId(owner_profile_id)
    custom_list = CustomList.create(profile_id=owner, name="Seeded", existing_count=0).with_updates(
        item_count=len(media_ids)
    )
    if shared:
        custom_list = custom_list.shared()
    async with session_factory() as session:
        repo = SQLAlchemyCustomListRepository(session)
        saved = await repo.add(custom_list)
        assert saved.id is not None
        for position, media_id in enumerate(media_ids):
            await repo.add_item(
                saved.id.value,
                CustomListItem.create(
                    media_id=media_id, media_type=MediaType.MOVIE, position=position
                ),
                owner,
            )
        await session.commit()
    return saved


def _ids(response: Response) -> list[str]:
    return [item["media_id"] for item in response.json()["data"]]


@pytest.mark.e2e
class TestListReadsUnderMaturityLimit:
    """Every list read drops titles above the limit and leaves no trace of them."""

    async def test_watchlist_hides_title_and_refills_the_limit(
        self,
        app: FastAPI,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        now = datetime.now(UTC)
        await _seed_watchlist(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=ids[_TEN_TITLE],
            added_at=now - timedelta(hours=1),
        )
        await _seed_watchlist(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=ids[_SIXTEEN_TITLE],
            added_at=now,
        )

        unlimited = await client.get(WATCHLIST_PATH, params={"limit": 1})
        with _maturity_limit(app):
            limited = await client.get(WATCHLIST_PATH, params={"limit": 1})

        assert unlimited.status_code == limited.status_code == 200
        assert _ids(unlimited) == [ids[_SIXTEEN_TITLE]]
        assert _ids(limited) == [ids[_TEN_TITLE]]
        assert _SIXTEEN_TITLE not in limited.text
        assert ids[_SIXTEEN_TITLE] not in limited.text
        assert limited.json().keys() == unlimited.json().keys()
        assert limited.json()["data"][0].keys() == unlimited.json()["data"][0].keys()

    async def test_owner_list_hides_title_without_changing_hidden_count(
        self,
        app: FastAPI,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        custom_list = await _seed_list(
            session_factory,
            owner_profile_id=user.profile_external_id,
            media_ids=[ids[_SIXTEEN_TITLE], ids[_OTHER_SHELF_TITLE], ids[_TEN_TITLE]],
        )
        path = f"{CUSTOM_LISTS_PATH}/{custom_list.id}/items"

        unlimited = await client.get(path)
        with _maturity_limit(app):
            limited = await client.get(path)

        assert unlimited.status_code == limited.status_code == 200
        assert _ids(unlimited) == [ids[_SIXTEEN_TITLE], ids[_TEN_TITLE]]
        assert _ids(limited) == [ids[_TEN_TITLE]]
        assert _SIXTEEN_TITLE not in limited.text
        # Only the other shelf counts, with or without the limit.
        assert limited.json()["metadata"] == unlimited.json()["metadata"] == {"hidden_count": 1}
        # Stored positions without a limit; renumbered under one.
        assert [item["position"] for item in unlimited.json()["data"]] == [0, 2]
        assert [item["position"] for item in limited.json()["data"]] == [0]
        assert limited.json().keys() == unlimited.json().keys()
        assert limited.json()["data"][0].keys() == unlimited.json()["data"][0].keys()

    async def test_shared_preview_hides_title_from_items_and_count(
        self,
        app: FastAPI,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        shared = await _seed_list(
            session_factory,
            owner_profile_id=ProfileId.generate().value,
            media_ids=[ids[_SIXTEEN_TITLE], ids[_OTHER_SHELF_TITLE], ids[_TEN_TITLE]],
            shared=True,
        )
        assert shared.share_token is not None
        path = f"{CUSTOM_LISTS_PATH}/shared/{shared.share_token.value}"

        unlimited = await client.get(path)
        with _maturity_limit(app):
            limited = await client.get(path)

        assert unlimited.status_code == limited.status_code == 200
        unlimited_data, limited_data = unlimited.json()["data"], limited.json()["data"]
        assert [item["media_id"] for item in unlimited_data["items"]] == [
            ids[_SIXTEEN_TITLE],
            ids[_TEN_TITLE],
        ]
        assert [item["media_id"] for item in limited_data["items"]] == [ids[_TEN_TITLE]]
        assert _SIXTEEN_TITLE not in limited.text
        assert limited_data["hidden_count"] == unlimited_data["hidden_count"] == 1
        assert unlimited_data["list"]["item_count"] == 3
        assert limited_data["list"]["item_count"] == 2
        assert limited_data.keys() == unlimited_data.keys()
        assert limited_data["list"].keys() == unlimited_data["list"].keys()
        assert "withheld" not in limited.text

    async def test_no_list_read_answers_401_for_restricted_titles(
        self,
        app: FastAPI,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """An unexpected 401 logs the web client out, so a refusal must never be one."""
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        await _seed_watchlist(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=ids[_SIXTEEN_TITLE],
            added_at=datetime.now(UTC),
        )
        owned = await _seed_list(
            session_factory,
            owner_profile_id=user.profile_external_id,
            media_ids=[ids[_SIXTEEN_TITLE]],
        )
        shared = await _seed_list(
            session_factory,
            owner_profile_id=ProfileId.generate().value,
            media_ids=[ids[_SIXTEEN_TITLE]],
            shared=True,
        )
        assert shared.share_token is not None

        with _maturity_limit(app):
            responses = [
                await client.get(WATCHLIST_PATH),
                await client.get(f"{CUSTOM_LISTS_PATH}/{owned.id}/items"),
                await client.get(f"{CUSTOM_LISTS_PATH}/shared/{shared.share_token.value}"),
            ]

        assert [r.status_code for r in responses] == [200, 200, 200]
        assert all(_SIXTEEN_TITLE not in r.text for r in responses)


@pytest.mark.e2e
class TestListReadsWithProductionPolicy:
    """Without an override the profile's own ACL decides, through the real adapter."""

    async def test_watchlist_lists_only_titles_within_the_acl(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        now = datetime.now(UTC)
        await _seed_watchlist(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=ids[_TEN_TITLE],
            added_at=now - timedelta(hours=1),
        )
        await _seed_watchlist(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=ids[_OTHER_SHELF_TITLE],
            added_at=now,
        )

        response = await client.get(WATCHLIST_PATH, params={"limit": 1})

        assert response.status_code == 200
        assert _ids(response) == [ids[_TEN_TITLE]]
        assert _OTHER_SHELF_TITLE not in response.text


@pytest.mark.e2e
class TestListReadsWithProfileMaturityLimit:
    """No override: the limit stored on the profile is what the reads apply."""

    async def test_watchlist_omits_title_above_the_profile_limit(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(
            allowed_library_ids=[_LIBRARY_ID], maturity_limit=_LIMIT
        )
        now = datetime.now(UTC)
        await _seed_watchlist(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=ids[_TEN_TITLE],
            added_at=now - timedelta(hours=1),
        )
        await _seed_watchlist(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=ids[_SIXTEEN_TITLE],
            added_at=now,
        )

        response = await client.get(WATCHLIST_PATH)

        assert response.status_code == 200
        assert _ids(response) == [ids[_TEN_TITLE]]
        assert _SIXTEEN_TITLE not in response.text
        assert ids[_SIXTEEN_TITLE] not in response.text
