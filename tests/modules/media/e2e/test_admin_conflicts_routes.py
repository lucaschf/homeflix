"""End-to-end tests for ``GET /api/v1/admin/conflicts`` (ADR-015 Phase 1)."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    MediaConflict,
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
