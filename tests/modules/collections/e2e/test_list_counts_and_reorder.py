"""End-to-end tests for list counts and reorder under a maturity limit (ADR-035).

Drives the real custom-list routes over the in-process ASGI transport
against an in-memory database.

Tests that need the age axis override the collections container's
``profile_viewing_policy`` provider with a policy that carries a limit,
to pin the contract independently of how a profile stores its limit;
the same requests without the override go through the real adapter,
which also proves the lists read and the rename are wired to the
provider and to the media lookup.

Rows are seeded straight through the repositories, as lists recorded
before a restriction would be.
"""

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.modules.collections.e2e.conftest import SeededUser

from src.modules.collections.application.ports import ProfileViewingPolicyPort
from src.modules.collections.domain.entities import CustomList, CustomListItem, ListFollow
from src.modules.collections.domain.value_objects import ListId
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyCustomListRepository,
    SQLAlchemyListFollowRepository,
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

CUSTOM_LISTS_PATH = "/api/v1/custom-lists"

_LIBRARY_ID = "lib_listcounts01"
_OTHER_LIBRARY_ID = "lib_otherlib0001"
_LIMIT = 12
_LIST_NAME = "Seeded"

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
    removed: bool = False,
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
        repo = SQLAlchemyMovieRepository(session)
        saved = await repo.save(movie)
        assert saved.id is not None
        if removed:
            await repo.delete(saved.id)
        await session.commit()
    return str(saved.id)


async def _seed_list(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    owner_profile_id: str,
    media_ids: list[str],
    shared: bool = False,
) -> CustomList:
    """Seed a list holding ``media_ids`` at positions ``0..n-1``, count in sync."""
    owner = ProfileId(owner_profile_id)
    custom_list = CustomList.create(
        profile_id=owner, name=_LIST_NAME, existing_count=0
    ).with_updates(item_count=len(media_ids))
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


async def _seed_follow(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    follower_profile_id: str,
    custom_list: CustomList,
) -> None:
    async with session_factory() as session:
        await SQLAlchemyListFollowRepository(session).add(
            ListFollow.create(
                follower_profile_id=ProfileId(follower_profile_id),
                list_id=ListId(str(custom_list.id)),
            )
        )
        await session.commit()


async def _seed_mixed_list(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    owner_profile_id: str,
    shared: bool = False,
    tag: str = "Owned",
) -> CustomList:
    """A list with one title of each kind: 16+, visible, other shelf, removed."""
    return await _seed_list(
        session_factory,
        owner_profile_id=owner_profile_id,
        media_ids=[
            await _seed_movie(session_factory, title=f"{tag} Sixteen", age=16),
            await _seed_movie(session_factory, title=f"{tag} Ten", age=10),
            await _seed_movie(
                session_factory,
                title=f"{tag} Other Shelf",
                age=10,
                library_id=_OTHER_LIBRARY_ID,
            ),
            await _seed_movie(session_factory, title=f"{tag} Removed", age=10, removed=True),
        ],
        shared=shared,
    )


_REMOVED_PER_MIXED_LIST = 1


def _row(response: Response, list_id: str) -> dict[str, object]:
    return next(row for row in response.json()["data"] if row["id"] == list_id)


def _invariant(item_count: object, items: Response) -> int:
    """``item_count - len(items) - hidden_count``, which must equal the removed titles."""
    assert isinstance(item_count, int)
    body = items.json()
    return item_count - len(body["data"]) - body["metadata"]["hidden_count"]


@pytest.mark.e2e
class TestListCountsUnderMaturityLimit:
    """Counts leave out titles withheld by age — and only those."""

    async def test_owned_and_followed_counts_agree_with_items_and_preview(
        self,
        app: FastAPI,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        owned = await _seed_mixed_list(session_factory, owner_profile_id=user.profile_external_id)
        followed = await _seed_mixed_list(
            session_factory,
            owner_profile_id=ProfileId.generate().value,
            shared=True,
            tag="Followed",
        )
        await _seed_follow(
            session_factory, follower_profile_id=user.profile_external_id, custom_list=followed
        )
        assert followed.share_token is not None
        owned_items_path = f"{CUSTOM_LISTS_PATH}/{owned.id}/items"
        followed_items_path = f"{CUSTOM_LISTS_PATH}/{followed.id}/items"

        unlimited = await client.get(CUSTOM_LISTS_PATH)
        with _maturity_limit(app):
            limited = await client.get(CUSTOM_LISTS_PATH)
            owned_items = await client.get(owned_items_path)
            followed_items = await client.get(followed_items_path)
            preview = await client.get(f"{CUSTOM_LISTS_PATH}/shared/{followed.share_token.value}")

        responses = [unlimited, limited, owned_items, followed_items, preview]
        assert [r.status_code for r in responses] == [200] * 5
        # Without a limit: the stored count, other shelf and removed included.
        assert _row(unlimited, str(owned.id))["item_count"] == 4
        assert _row(unlimited, str(followed.id))["item_count"] == 4
        # Under the limit only the 16+ title leaves the count.
        owned_row = _row(limited, str(owned.id))
        followed_row = _row(limited, str(followed.id))
        assert owned_row["item_count"] == followed_row["item_count"] == 3
        assert _invariant(owned_row["item_count"], owned_items) == _REMOVED_PER_MIXED_LIST
        assert _invariant(followed_row["item_count"], followed_items) == _REMOVED_PER_MIXED_LIST
        assert followed_row["item_count"] == preview.json()["data"]["list"]["item_count"]
        assert limited.json().keys() == unlimited.json().keys()
        assert owned_row.keys() == _row(unlimited, str(owned.id)).keys()
        assert followed_row["is_followed"] is True

    async def test_rename_returns_the_count_the_lists_read_shows(
        self,
        app: FastAPI,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        owned = await _seed_mixed_list(session_factory, owner_profile_id=user.profile_external_id)
        path = f"{CUSTOM_LISTS_PATH}/{owned.id}"

        unlimited = await client.patch(path, json={"name": _LIST_NAME})
        with _maturity_limit(app):
            limited = await client.patch(path, json={"name": "Renamed"})
            items = await client.get(f"{path}/items")

        assert [unlimited.status_code, limited.status_code, items.status_code] == [200] * 3
        assert unlimited.json()["data"]["item_count"] == 4
        limited_data = limited.json()["data"]
        assert limited_data["name"] == "Renamed"
        assert limited_data["item_count"] == 3
        assert _invariant(limited_data["item_count"], items) == _REMOVED_PER_MIXED_LIST
        assert limited_data.keys() == unlimited.json()["data"].keys()

    async def test_partial_reorder_keeps_the_withheld_titles_in_their_slots(
        self,
        app: FastAPI,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        a = await _seed_movie(session_factory, title="A", age=10)
        h1 = await _seed_movie(session_factory, title="H1", age=16)
        b = await _seed_movie(session_factory, title="B", age=10)
        h2 = await _seed_movie(session_factory, title="H2", age=18)
        c = await _seed_movie(session_factory, title="C", age=10)
        owned = await _seed_list(
            session_factory,
            owner_profile_id=user.profile_external_id,
            media_ids=[a, h1, b, h2, c],
        )
        items_path = f"{CUSTOM_LISTS_PATH}/{owned.id}/items"

        with _maturity_limit(app):
            seen = await client.get(items_path)
            reorder = await client.patch(f"{items_path}/order", json={"media_ids": [c, a, b]})
            seen_after = await client.get(items_path)
        stored = await client.get(items_path)

        assert [seen.status_code, seen_after.status_code, stored.status_code] == [200] * 3
        assert reorder.status_code == 204
        assert [item["media_id"] for item in seen.json()["data"]] == [a, b, c]
        assert [item["media_id"] for item in seen_after.json()["data"]] == [c, a, b]
        assert [(item["media_id"], item["position"]) for item in stored.json()["data"]] == [
            (c, 0),
            (h1, 1),
            (a, 2),
            (h2, 3),
            (b, 4),
        ]


@pytest.mark.e2e
class TestListCountsWithProductionPolicy:
    """Without an override the profile's own ACL decides, through the real adapter."""

    async def test_lists_read_and_rename_show_the_stored_count(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        owned = await _seed_mixed_list(session_factory, owner_profile_id=user.profile_external_id)

        lists = await client.get(CUSTOM_LISTS_PATH)
        renamed = await client.patch(f"{CUSTOM_LISTS_PATH}/{owned.id}", json={"name": "Renamed"})

        assert [lists.status_code, renamed.status_code] == [200, 200]
        assert _row(lists, str(owned.id))["item_count"] == 4
        assert renamed.json()["data"]["item_count"] == 4
