"""End-to-end tests for the viewing policy on collections writes (ADR-035).

Drives the real watchlist and custom-list write routes over the
in-process ASGI transport against an in-memory database.

The first class overrides the collections container's
``profile_viewing_policy`` provider with a policy that carries a limit,
to pin the age axis end to end independently of how a profile stores
its limit. The second class runs
without the override, so it also proves the composition root hands the
container an Identity UoW factory and that the write use cases are wired
to the provider and to the media lookup.

Entries that already exist are seeded straight through the repositories,
as rows recorded before a restriction would be.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.modules.collections.e2e.conftest import SeededUser

from src.modules.collections.application.ports import ProfileViewingPolicyPort
from src.modules.collections.domain.entities import CustomList, CustomListItem, WatchlistItem
from src.modules.collections.domain.value_objects import ListId
from src.modules.collections.infrastructure.persistence.models import (
    CustomListItemModel,
    CustomListModel,
    WatchlistItemModel,
)
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
TOGGLE_PATH = f"{WATCHLIST_PATH}/toggle"
CUSTOM_LISTS_PATH = "/api/v1/custom-lists"

_LIBRARY_ID = "lib_writesgate01"
_OTHER_LIBRARY_ID = "lib_otherlib0001"
_LIMIT = 12
_MISSING_MOVIE_ID = "mov_missing00000"

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


@pytest.fixture(scope="function")
async def limited_profile(app: FastAPI) -> AsyncGenerator[None, None]:
    """Resolve every profile to one library with a maturity limit of 12."""
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
    yield
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
    session_factory: async_sessionmaker[AsyncSession], *, profile_id: str, media_id: str
) -> None:
    async with session_factory() as session:
        await SQLAlchemyWatchlistRepository(session).add(
            WatchlistItem(
                id=ListId.generate(),
                profile_id=ProfileId(profile_id),
                media_id=media_id,
                media_type=MediaType.MOVIE,
                added_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def _seed_list(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    owner_profile_id: str,
    media_ids: list[str],
) -> str:
    """Seed a list holding ``media_ids`` at positions ``0..n-1``, count in sync."""
    owner = ProfileId(owner_profile_id)
    custom_list = CustomList.create(profile_id=owner, name="Seeded", existing_count=0).with_updates(
        item_count=len(media_ids)
    )
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
    return saved.id.value


async def _live_watchlist_media_ids(session_factory: async_sessionmaker[AsyncSession]) -> set[str]:
    async with session_factory() as session:
        result = await session.execute(
            select(WatchlistItemModel.media_id).where(WatchlistItemModel.deleted_at.is_(None))
        )
        return set(result.scalars())


async def _live_list_state(
    session_factory: async_sessionmaker[AsyncSession], list_id: str
) -> tuple[set[str], int]:
    """The list's live item ids and its stored item count."""
    async with session_factory() as session:
        custom_list = (
            await session.execute(
                select(CustomListModel).where(CustomListModel.external_id == list_id)
            )
        ).scalar_one()
        result = await session.execute(
            select(CustomListItemModel.media_id).where(
                CustomListItemModel.custom_list_id == custom_list.id,
                CustomListItemModel.deleted_at.is_(None),
            )
        )
        return set(result.scalars()), custom_list.item_count


def _body(media_id: str) -> dict[str, str]:
    return {"media_id": media_id, "media_type": "movie"}


def _assert_same_bytes_as_missing(
    response: Response, missing: Response, *, requested_id: str
) -> None:
    """The refusal must be indistinguishable from a title that does not exist.

    The raw bodies are compared; the only difference allowed is the id
    each request itself sent.
    """
    assert missing.status_code == 404
    assert response.status_code == 404
    assert response.content.replace(requested_id.encode(), b"<id>") == missing.content.replace(
        _MISSING_MOVIE_ID.encode(), b"<id>"
    )


@pytest.mark.e2e
@pytest.mark.usefixtures("limited_profile")
class TestWritesUnderMaturityLimit:
    """Write routes under a policy with one library and a limit of 12."""

    async def test_toggle_add_above_limit_is_404_like_a_missing_movie(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        restricted = await client.post(TOGGLE_PATH, json=_body(ids[_SIXTEEN_TITLE]))
        missing = await client.post(TOGGLE_PATH, json=_body(_MISSING_MOVIE_ID))
        listed = await client.get(WATCHLIST_PATH)

        _assert_same_bytes_as_missing(restricted, missing, requested_id=ids[_SIXTEEN_TITLE])
        assert _SIXTEEN_TITLE not in restricted.text
        assert await _live_watchlist_media_ids(session_factory) == set()
        assert listed.status_code == 200
        assert listed.json()["data"] == []

    async def test_toggle_add_other_library_is_404_like_a_missing_movie(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        restricted = await client.post(TOGGLE_PATH, json=_body(ids[_OTHER_SHELF_TITLE]))
        missing = await client.post(TOGGLE_PATH, json=_body(_MISSING_MOVIE_ID))

        _assert_same_bytes_as_missing(restricted, missing, requested_id=ids[_OTHER_SHELF_TITLE])
        assert await _live_watchlist_media_ids(session_factory) == set()

    async def test_toggle_add_within_limit_returns_200(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        response = await client.post(TOGGLE_PATH, json=_body(ids[_TEN_TITLE]))
        check = await client.get(f"{WATCHLIST_PATH}/check/{ids[_TEN_TITLE]}")

        assert response.status_code == 200
        assert response.json()["data"] == {"media_id": ids[_TEN_TITLE], "added": True}
        assert check.json()["data"] == {"in_list": True}
        assert await _live_watchlist_media_ids(session_factory) == {ids[_TEN_TITLE]}

    async def test_toggle_removes_an_existing_entry_above_limit(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        await _seed_watchlist(
            session_factory, profile_id=user.profile_external_id, media_id=ids[_SIXTEEN_TITLE]
        )

        response = await client.post(TOGGLE_PATH, json=_body(ids[_SIXTEEN_TITLE]))

        assert response.status_code == 200
        assert response.json()["data"] == {"media_id": ids[_SIXTEEN_TITLE], "added": False}
        assert await _live_watchlist_media_ids(session_factory) == set()

    async def test_check_of_an_existing_entry_above_limit_reads_as_absent(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        await _seed_watchlist(
            session_factory, profile_id=user.profile_external_id, media_id=ids[_SIXTEEN_TITLE]
        )

        hidden = await client.get(f"{WATCHLIST_PATH}/check/{ids[_SIXTEEN_TITLE]}")
        absent = await client.get(f"{WATCHLIST_PATH}/check/{ids[_TEN_TITLE]}")

        assert hidden.status_code == absent.status_code == 200
        assert hidden.json()["data"] == absent.json()["data"] == {"in_list": False}

    async def test_add_item_above_limit_is_404_like_a_missing_movie(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        list_id = await _seed_list(
            session_factory, owner_profile_id=user.profile_external_id, media_ids=[]
        )
        path = f"{CUSTOM_LISTS_PATH}/{list_id}/items"

        restricted = await client.post(path, json=_body(ids[_SIXTEEN_TITLE]))
        missing = await client.post(path, json=_body(_MISSING_MOVIE_ID))
        listed = await client.get(path)

        _assert_same_bytes_as_missing(restricted, missing, requested_id=ids[_SIXTEEN_TITLE])
        assert _SIXTEEN_TITLE not in restricted.text
        assert await _live_list_state(session_factory, list_id) == (set(), 0)
        assert listed.status_code == 200
        assert listed.json()["data"] == []

    async def test_add_item_other_library_is_404_like_a_missing_movie(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        list_id = await _seed_list(
            session_factory, owner_profile_id=user.profile_external_id, media_ids=[]
        )
        path = f"{CUSTOM_LISTS_PATH}/{list_id}/items"

        restricted = await client.post(path, json=_body(ids[_OTHER_SHELF_TITLE]))
        missing = await client.post(path, json=_body(_MISSING_MOVIE_ID))

        _assert_same_bytes_as_missing(restricted, missing, requested_id=ids[_OTHER_SHELF_TITLE])
        assert await _live_list_state(session_factory, list_id) == (set(), 0)

    async def test_add_item_above_limit_already_in_the_list_is_404_not_duplicate(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        list_id = await _seed_list(
            session_factory,
            owner_profile_id=user.profile_external_id,
            media_ids=[ids[_SIXTEEN_TITLE]],
        )
        path = f"{CUSTOM_LISTS_PATH}/{list_id}/items"

        restricted = await client.post(path, json=_body(ids[_SIXTEEN_TITLE]))
        missing = await client.post(path, json=_body(_MISSING_MOVIE_ID))

        _assert_same_bytes_as_missing(restricted, missing, requested_id=ids[_SIXTEEN_TITLE])
        assert await _live_list_state(session_factory, list_id) == ({ids[_SIXTEEN_TITLE]}, 1)

    async def test_add_item_to_someone_elses_list_is_404_for_the_list(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        foreign_list = await _seed_list(
            session_factory, owner_profile_id=ProfileId.generate().value, media_ids=[]
        )

        restricted = await client.post(
            f"{CUSTOM_LISTS_PATH}/{foreign_list}/items", json=_body(ids[_SIXTEEN_TITLE])
        )
        visible = await client.post(
            f"{CUSTOM_LISTS_PATH}/{foreign_list}/items", json=_body(ids[_TEN_TITLE])
        )

        assert restricted.status_code == visible.status_code == 404
        assert restricted.content.replace(ids[_SIXTEEN_TITLE].encode(), b"<id>") == (
            visible.content.replace(ids[_TEN_TITLE].encode(), b"<id>")
        )
        assert restricted.json()["code"] == visible.json()["code"]
        assert foreign_list in restricted.text

    async def test_add_item_within_limit_returns_201(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        list_id = await _seed_list(
            session_factory, owner_profile_id=user.profile_external_id, media_ids=[]
        )

        response = await client.post(
            f"{CUSTOM_LISTS_PATH}/{list_id}/items", json=_body(ids[_TEN_TITLE])
        )

        assert response.status_code == 201
        assert response.json()["data"] == {
            "list_id": list_id,
            "media_id": ids[_TEN_TITLE],
            "added": True,
        }
        assert await _live_list_state(session_factory, list_id) == ({ids[_TEN_TITLE]}, 1)

    async def test_remove_item_above_limit_returns_204(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        list_id = await _seed_list(
            session_factory,
            owner_profile_id=user.profile_external_id,
            media_ids=[ids[_SIXTEEN_TITLE]],
        )

        response = await client.delete(f"{CUSTOM_LISTS_PATH}/{list_id}/items/{ids[_SIXTEEN_TITLE]}")

        assert response.status_code == 204
        live_items, _ = await _live_list_state(session_factory, list_id)
        assert live_items == set()

    async def test_no_write_route_answers_401_for_restricted_titles(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """An unexpected 401 logs the web client out, so a refusal must never be one."""
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        list_id = await _seed_list(
            session_factory, owner_profile_id=user.profile_external_id, media_ids=[]
        )
        sixteen = ids[_SIXTEEN_TITLE]

        responses = [
            await client.post(TOGGLE_PATH, json=_body(sixteen)),
            await client.post(TOGGLE_PATH, json=_body(_MISSING_MOVIE_ID)),
            await client.get(f"{WATCHLIST_PATH}/check/{sixteen}"),
            await client.post(f"{CUSTOM_LISTS_PATH}/{list_id}/items", json=_body(sixteen)),
            await client.post(
                f"{CUSTOM_LISTS_PATH}/{list_id}/items", json=_body(_MISSING_MOVIE_ID)
            ),
        ]

        assert [r.status_code for r in responses] == [404, 404, 200, 404, 404]


@pytest.mark.e2e
class TestWritesWithProductionPolicy:
    """Without an override the profile's own ACL decides, through the real adapter."""

    async def test_toggle_within_acl_adds_and_outside_acl_is_404(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        within = await client.post(TOGGLE_PATH, json=_body(ids[_SIXTEEN_TITLE]))
        outside = await client.post(TOGGLE_PATH, json=_body(ids[_OTHER_SHELF_TITLE]))
        check = await client.get(f"{WATCHLIST_PATH}/check/{ids[_SIXTEEN_TITLE]}")

        assert within.status_code == 200
        assert within.json()["data"]["added"] is True
        assert outside.status_code == 404
        assert check.json()["data"] == {"in_list": True}
        assert await _live_watchlist_media_ids(session_factory) == {ids[_SIXTEEN_TITLE]}

    async def test_add_item_within_acl_returns_201_and_outside_acl_is_404(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed_catalog(session_factory)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        list_id = await _seed_list(
            session_factory, owner_profile_id=user.profile_external_id, media_ids=[]
        )
        path = f"{CUSTOM_LISTS_PATH}/{list_id}/items"

        within = await client.post(path, json=_body(ids[_SIXTEEN_TITLE]))
        outside = await client.post(path, json=_body(ids[_OTHER_SHELF_TITLE]))

        assert within.status_code == 201
        assert outside.status_code == 404
        assert await _live_list_state(session_factory, list_id) == ({ids[_SIXTEEN_TITLE]}, 1)
