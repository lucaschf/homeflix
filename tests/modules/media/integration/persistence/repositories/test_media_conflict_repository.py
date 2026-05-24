"""Integration tests for SqlAlchemyMediaConflictRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    MediaConflict,
    ResolutionAction,
    ResolutionSource,
)
from src.modules.media.infrastructure.persistence.repositories.media_conflict_repository import (
    SqlAlchemyMediaConflictRepository,
)


def _new_conflict(
    *,
    a_id: str = "mov_aaaaaaaaaaaa",
    b_id: str = "mov_bbbbbbbbbbbb",
) -> MediaConflict:
    return MediaConflict.detect(
        candidate_a_id=a_id,
        candidate_a_type="movie",
        candidate_a_runtime_minutes=120.0,
        candidate_b_id=b_id,
        candidate_b_type="movie",
        candidate_b_runtime_minutes=125.0,
        match_reason=MatchReason.TMDB_ID,
    )


@pytest.mark.integration
class TestSaveAndFind:
    async def test_save_assigns_external_id_on_first_persist(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SqlAlchemyMediaConflictRepository(db_session)
        saved = await repo.save(_new_conflict())

        assert saved.id is not None
        assert str(saved.id).startswith("cnf_")
        assert saved.resolved_at is None

    async def test_save_updates_in_place_after_resolution(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SqlAlchemyMediaConflictRepository(db_session)
        saved = await repo.save(_new_conflict())

        resolved = saved.resolve(ResolutionAction.MARK_DISTINCT)
        await repo.save(resolved)
        again = await repo.find_by_id(saved.id)  # type: ignore[arg-type]

        assert again is not None
        assert again.is_resolved is True
        assert again.resolution is ResolutionAction.MARK_DISTINCT


@pytest.mark.integration
class TestFindBlockingPair:
    async def test_returns_match_when_orientation_swapped(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SqlAlchemyMediaConflictRepository(db_session)
        original = await repo.save(_new_conflict(a_id="mov_aaaaaaaaaaaa", b_id="mov_bbbbbbbbbbbb"))

        # Same pair, reversed ids.
        result = await repo.find_blocking_pair(
            "mov_bbbbbbbbbbbb",
            "mov_aaaaaaaaaaaa",
        )

        assert result is not None
        assert result.id == original.id

    async def test_merge_resolved_pair_does_not_block(
        self,
        db_session: AsyncSession,
    ) -> None:
        # MERGE-resolved rows must not suppress re-queueing: by the
        # time we look up the pair the loser is soft-deleted, so the
        # detector cannot rediscover it anyway. The aggregate is
        # excluded so a re-import under a fresh id can be detected.
        repo = SqlAlchemyMediaConflictRepository(db_session)
        saved = await repo.save(_new_conflict())
        await repo.save(
            saved.resolve(ResolutionAction.MERGE_REPLACE, winner_id=saved.candidate_a_id)
        )

        result = await repo.find_blocking_pair(
            saved.candidate_a_id,
            saved.candidate_b_id,
        )

        assert result is None

    async def test_mark_distinct_pair_blocks_re_queueing(
        self,
        db_session: AsyncSession,
    ) -> None:
        # MARK_DISTINCT is the operator's "do not re-flag this pair"
        # verdict; it must persist across future enrich passes.
        repo = SqlAlchemyMediaConflictRepository(db_session)
        saved = await repo.save(_new_conflict())
        resolved = await repo.save(saved.resolve(ResolutionAction.MARK_DISTINCT))

        result = await repo.find_blocking_pair(
            saved.candidate_a_id,
            saved.candidate_b_id,
        )

        assert result is not None
        assert result.id == resolved.id
        assert result.is_marked_distinct is True

    async def test_returns_none_when_pair_is_unknown(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SqlAlchemyMediaConflictRepository(db_session)
        result = await repo.find_blocking_pair("mov_aaaaaaaaaaaa", "mov_bbbbbbbbbbbb")
        assert result is None


@pytest.mark.integration
class TestListPending:
    async def test_excludes_resolved_rows(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SqlAlchemyMediaConflictRepository(db_session)
        pending = await repo.save(_new_conflict(a_id="mov_aaaaaaaaaaaa", b_id="mov_bbbbbbbbbbbb"))
        resolved = await repo.save(_new_conflict(a_id="mov_cccccccccccc", b_id="mov_dddddddddddd"))
        await repo.save(
            resolved.resolve(
                ResolutionAction.MERGE_KEEP_BOTH,
                winner_id=resolved.candidate_a_id,
            ),
        )

        page = await repo.list_pending(limit=10)

        assert [c.id for c in page.items] == [pending.id]

    async def test_pagination_advances_via_cursor(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SqlAlchemyMediaConflictRepository(db_session)
        # Insert 3 conflicts with distinct pairs so insertion order
        # determines the newest-first ordering.
        c1 = await repo.save(_new_conflict(a_id="mov_aaaaaaaaaaaa", b_id="mov_bbbbbbbbbbbb"))
        c2 = await repo.save(_new_conflict(a_id="mov_cccccccccccc", b_id="mov_dddddddddddd"))
        c3 = await repo.save(_new_conflict(a_id="mov_eeeeeeeeeeee", b_id="mov_ffffffffffff"))

        first_page = await repo.list_pending(limit=2)
        assert [c.id for c in first_page.items] == [c3.id, c2.id]
        assert first_page.pagination.has_more is True
        assert first_page.pagination.next_cursor is not None

        second_page = await repo.list_pending(
            cursor=first_page.pagination.next_cursor,
            limit=2,
        )
        assert [c.id for c in second_page.items] == [c1.id]
        assert second_page.pagination.has_more is False


@pytest.mark.integration
class TestListResolved:
    """ADR-015 Phase 3 — audit view of resolved conflicts."""

    async def test_excludes_pending_rows(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SqlAlchemyMediaConflictRepository(db_session)
        # Pending: not in result.
        await repo.save(_new_conflict(a_id="mov_aaaaaaaaaaaa", b_id="mov_bbbbbbbbbbbb"))
        # Resolved manual:
        manual = await repo.save(_new_conflict(a_id="mov_cccccccccccc", b_id="mov_dddddddddddd"))
        await repo.save(
            manual.resolve(ResolutionAction.MARK_DISTINCT),
        )

        page = await repo.list_resolved()

        # Only the resolved row appears (pending excluded).
        assert len(page.items) == 1
        assert page.items[0].is_resolved is True

    async def test_filters_by_source_auto(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SqlAlchemyMediaConflictRepository(db_session)
        # Manual resolution:
        manual = await repo.save(_new_conflict(a_id="mov_aaaaaaaaaaaa", b_id="mov_bbbbbbbbbbbb"))
        await repo.save(manual.resolve(ResolutionAction.MARK_DISTINCT))
        # Auto resolution:
        auto = await repo.save(_new_conflict(a_id="mov_cccccccccccc", b_id="mov_dddddddddddd"))
        auto_resolved = await repo.save(
            auto.resolve(
                ResolutionAction.MERGE_REPLACE,
                winner_id=auto.candidate_a_id,
                source=ResolutionSource.AUTO,
            ),
        )

        page = await repo.list_resolved(source=ResolutionSource.AUTO)

        assert [c.id for c in page.items] == [auto_resolved.id]
        assert page.items[0].resolution_source is ResolutionSource.AUTO

    async def test_source_none_returns_both_sources(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SqlAlchemyMediaConflictRepository(db_session)
        manual = await repo.save(_new_conflict(a_id="mov_aaaaaaaaaaaa", b_id="mov_bbbbbbbbbbbb"))
        await repo.save(manual.resolve(ResolutionAction.MARK_DISTINCT))
        auto = await repo.save(_new_conflict(a_id="mov_cccccccccccc", b_id="mov_dddddddddddd"))
        await repo.save(
            auto.resolve(
                ResolutionAction.MERGE_REPLACE,
                winner_id=auto.candidate_a_id,
                source=ResolutionSource.AUTO,
            ),
        )

        page = await repo.list_resolved()

        assert len(page.items) == 2
        sources = {c.resolution_source for c in page.items}
        assert sources == {ResolutionSource.MANUAL, ResolutionSource.AUTO}
