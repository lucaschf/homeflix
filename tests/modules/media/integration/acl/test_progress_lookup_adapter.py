"""Integration tests for the Media ProgressLookupAdapter."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.infrastructure.acl import ProgressLookupAdapter
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import WatchableMediaType
from src.modules.watch_progress.infrastructure.persistence.repositories import (
    SQLAlchemyWatchProgressRepository,
)
from src.modules.watch_progress.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyWatchProgressUnitOfWorkFactory,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


def _progress(
    media_id: str,
    position: int = 1800,
    duration: int = 3600,
    media_type: WatchableMediaType = WatchableMediaType.EPISODE,
) -> WatchProgress:
    return WatchProgress.create(
        profile_id=_PROFILE_ID,
        media_id=media_id,
        media_type=media_type,
        position_seconds=position,
        duration_seconds=duration,
    )


def _make_adapter(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    default_profile_id: str | None = _PROFILE_ID.value,
) -> ProgressLookupAdapter:
    return ProgressLookupAdapter(
        SqlAlchemyWatchProgressUnitOfWorkFactory(session_factory),
        default_profile_id=default_profile_id,
    )


@pytest.mark.integration
class TestProgressLookupAdapter:
    """The adapter exposes ProgressSummary without leaking domain types."""

    async def test_find_for_media_ids_returns_summaries(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        progress_repo = SQLAlchemyWatchProgressRepository(db_session)
        await progress_repo.save(_progress("epi_ser_ABC_1_1", position=900))
        await progress_repo.save(_progress("epi_ser_ABC_1_2", position=3300))
        await db_session.commit()

        adapter = _make_adapter(session_factory)

        result = await adapter.find_for_media_ids(
            ["epi_ser_ABC_1_1", "epi_ser_ABC_1_2", "epi_ser_ABC_1_3"],
        )

        assert set(result.keys()) == {"epi_ser_ABC_1_1", "epi_ser_ABC_1_2"}
        assert result["epi_ser_ABC_1_1"].position_seconds == 900
        assert result["epi_ser_ABC_1_1"].percentage == pytest.approx(25.0)
        assert result["epi_ser_ABC_1_2"].status == "completed"

    async def test_find_for_media_ids_with_empty_input(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        adapter = _make_adapter(session_factory)

        assert await adapter.find_for_media_ids([]) == {}

    async def test_find_for_media_ids_returns_empty_when_no_default_profile(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Strict transition mode: no default_profile_id -> graceful
        # degradation, even when matching rows exist.
        progress_repo = SQLAlchemyWatchProgressRepository(db_session)
        await progress_repo.save(_progress("epi_ser_ABC_1_1"))
        await db_session.commit()

        adapter = _make_adapter(session_factory, default_profile_id=None)

        assert await adapter.find_for_media_ids(["epi_ser_ABC_1_1"]) == {}

    async def test_progress_summary_includes_last_watched_at(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        progress_repo = SQLAlchemyWatchProgressRepository(db_session)
        await progress_repo.save(_progress("epi_ser_ABC_1_1"))
        await db_session.commit()

        adapter = _make_adapter(session_factory)
        result = await adapter.find_for_media_ids(["epi_ser_ABC_1_1"])

        summary = result["epi_ser_ABC_1_1"]
        assert summary.last_watched_at is not None
        assert summary.media_id == "epi_ser_ABC_1_1"
