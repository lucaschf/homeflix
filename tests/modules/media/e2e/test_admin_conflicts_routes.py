"""End-to-end tests for ``GET /api/v1/admin/conflicts`` (ADR-015 Phase 1)."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.domain.entities import Movie
from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    MediaConflict,
)
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
)
from src.modules.media.infrastructure.persistence.repositories.media_conflict_repository import (
    SqlAlchemyMediaConflictRepository,
)
from tests.modules.media.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
CONFLICTS_PATH = "/api/v1/admin/conflicts"


async def _login(client: AsyncClient, user: SeededUser) -> None:
    resp = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert resp.status_code == 204


async def _login_as_admin(
    client: AsyncClient,
    seed: Callable[..., Awaitable[SeededUser]],
) -> SeededUser:
    admin = await seed(email="admin@example.com", is_admin=True)
    await _login(client, admin)
    return admin


async def _seed_conflict(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    a_id: str,
    b_id: str,
) -> str:
    """Insert one pending conflict via the repository; return its id."""
    async with session_factory() as session:
        repo = SqlAlchemyMediaConflictRepository(session)
        conflict = MediaConflict.detect(
            candidate_a_id=a_id,
            candidate_a_type="movie",
            candidate_a_runtime_minutes=120.0,
            candidate_b_id=b_id,
            candidate_b_type="movie",
            candidate_b_runtime_minutes=130.0,
            match_reason=MatchReason.TMDB_ID,
        )
        saved = await repo.save(conflict)
        await session.commit()
        return str(saved.id)


async def _seed_movie(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    external_id: str,
    title: str,
    file_path: str,
) -> None:
    """Insert one Movie aggregate via the repository."""
    async with session_factory() as session:
        repo = SQLAlchemyMovieRepository(session)
        await repo.save(
            Movie(
                id=MovieId(external_id),
                library_id="lib_test12345678",
                title=Title(title),
                year=Year(2020),
                duration=Duration(7200),
                files=[
                    MediaFile(
                        file_path=FilePath(file_path),
                        file_size=1_000_000_000,
                        resolution=Resolution("1080p"),
                        is_primary=True,
                    ),
                ],
            ),
        )
        await session.commit()


async def _seed_pair_with_conflict(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    a_id: str = "mov_winnerwinaaa",
    b_id: str = "mov_loserloseraa",
) -> tuple[str, str, str]:
    """Convenience: seed both movies + a pending conflict between them."""
    await _seed_movie(
        session_factory,
        external_id=a_id,
        title="Winner Movie",
        file_path=f"/movies/{a_id}.mkv",
    )
    await _seed_movie(
        session_factory,
        external_id=b_id,
        title="Loser Movie",
        file_path=f"/movies/{b_id}.mkv",
    )
    conflict_id = await _seed_conflict(session_factory, a_id=a_id, b_id=b_id)
    return conflict_id, a_id, b_id


@pytest.mark.e2e
class TestAdminConflictsAuth:
    """Auth gate — ``current_admin_user`` rejects members + anon users."""

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(CONFLICTS_PATH)
        assert response.status_code == 401

    async def test_member_returns_403(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com", is_admin=False)
        await _login(client, member)

        response = await client.get(CONFLICTS_PATH)
        assert response.status_code == 403


@pytest.mark.e2e
class TestAdminConflictsList:
    """``GET /admin/conflicts`` surfaces the pending queue."""

    async def test_empty_queue_returns_empty_list(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)

        response = await client.get(CONFLICTS_PATH)

        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "list"
        assert body["data"] == []

    async def test_returns_seeded_conflict_row(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        conflict_id = await _seed_conflict(
            session_factory,
            a_id="mov_abcdefghijkl",
            b_id="mov_mnopqrstuvwx",
        )

        response = await client.get(CONFLICTS_PATH)

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 1
        row = body["data"][0]
        assert row["conflict_id"] == conflict_id
        assert row["candidate_a"]["media_id"] == "mov_abcdefghijkl"
        assert row["candidate_b"]["media_id"] == "mov_mnopqrstuvwx"
        assert row["match_reason"] == "tmdb_id"
        assert row["suggested_action"] in {
            "likely_same_release",
            "different_edit_suspected",
        }

    async def test_pagination_returns_next_cursor(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        await _seed_conflict(session_factory, a_id="mov_aaaaaaaaaaaa", b_id="mov_bbbbbbbbbbbb")
        await _seed_conflict(session_factory, a_id="mov_cccccccccccc", b_id="mov_dddddddddddd")
        await _seed_conflict(session_factory, a_id="mov_eeeeeeeeeeee", b_id="mov_ffffffffffff")

        response = await client.get(f"{CONFLICTS_PATH}?limit=2")

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 2
        assert body["metadata"]["pagination"]["has_more"] is True
        assert body["metadata"]["pagination"]["next_cursor"] is not None


@pytest.mark.e2e
class TestAdminConflictsResolveAuth:
    """``POST /admin/conflicts/{id}/resolve`` — auth gate."""

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        response = await client.post(
            f"{CONFLICTS_PATH}/cnf_xxxxxxxxxxxx/resolve",
            json={"action": "mark_distinct"},
        )
        assert response.status_code == 401

    async def test_member_returns_403(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com", is_admin=False)
        await _login(client, member)
        response = await client.post(
            f"{CONFLICTS_PATH}/cnf_xxxxxxxxxxxx/resolve",
            json={"action": "mark_distinct"},
        )
        assert response.status_code == 403


@pytest.mark.e2e
class TestAdminConflictsResolveSuccess:
    """``POST /admin/conflicts/{id}/resolve`` — happy paths."""

    async def test_mark_distinct_stamps_and_persists(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        conflict_id, _, _ = await _seed_pair_with_conflict(session_factory)

        response = await client.post(
            f"{CONFLICTS_PATH}/{conflict_id}/resolve",
            json={"action": "mark_distinct"},
        )

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["action"] == "mark_distinct"
        assert payload["winner_id"] is None
        assert payload["loser_id"] is None
        assert payload["variants_transferred"] == 0

        # The pending list now excludes it.
        list_resp = await client.get(CONFLICTS_PATH)
        assert list_resp.json()["data"] == []

    async def test_merge_replace_soft_deletes_loser(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        conflict_id, winner_id, loser_id = await _seed_pair_with_conflict(session_factory)

        response = await client.post(
            f"{CONFLICTS_PATH}/{conflict_id}/resolve",
            json={"action": "merge_replace", "winner_id": winner_id},
        )

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["winner_id"] == winner_id
        assert payload["loser_id"] == loser_id
        assert payload["variants_transferred"] == 0

        # Loser is soft-deleted; verify via repository lookup.
        async with session_factory() as session:
            repo = SQLAlchemyMovieRepository(session)
            assert await repo.find_by_id(MovieId(loser_id)) is None
            assert await repo.find_by_id(MovieId(winner_id)) is not None

    async def test_merge_keep_both_transfers_variants(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        conflict_id, winner_id, _ = await _seed_pair_with_conflict(session_factory)

        response = await client.post(
            f"{CONFLICTS_PATH}/{conflict_id}/resolve",
            json={"action": "merge_keep_both", "winner_id": winner_id},
        )

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["variants_transferred"] == 1


@pytest.mark.e2e
class TestAdminConflictsResolveFailures:
    """``POST /admin/conflicts/{id}/resolve`` — error paths."""

    async def test_unknown_conflict_returns_404(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        response = await client.post(
            f"{CONFLICTS_PATH}/cnf_doesnotexist/resolve",
            json={"action": "mark_distinct"},
        )
        assert response.status_code == 404

    async def test_already_resolved_returns_422(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Default mapping for BusinessRuleViolationException is 422.
        # If the operator wants 409 specifically for this rule code,
        # a per-BC override can be registered (ADR-012) later.
        await _login_as_admin(client, seed_user_with_profile)
        conflict_id, _, _ = await _seed_pair_with_conflict(session_factory)

        first = await client.post(
            f"{CONFLICTS_PATH}/{conflict_id}/resolve",
            json={"action": "mark_distinct"},
        )
        assert first.status_code == 200

        second = await client.post(
            f"{CONFLICTS_PATH}/{conflict_id}/resolve",
            json={"action": "mark_distinct"},
        )
        assert second.status_code == 422
        body = second.json()
        assert body["code"] == "BUSINESS_RULE_VIOLATION"
        assert "already resolved" in body["message"].lower()

    async def test_winner_not_in_pair_returns_422(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        conflict_id, _, _ = await _seed_pair_with_conflict(session_factory)

        response = await client.post(
            f"{CONFLICTS_PATH}/{conflict_id}/resolve",
            json={
                "action": "merge_replace",
                "winner_id": "mov_unrelatedaaa",
            },
        )
        assert response.status_code == 422
