"""Integration tests for the Media ProgressLookupAdapter."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.infrastructure.acl import ProgressLookupAdapter
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import WatchableMediaType
from src.modules.watch_progress.infrastructure.persistence.repositories import (
    SQLAlchemyWatchProgressRepository,
)


def _progress(
    media_id: str,
    position: int = 1800,
    duration: int = 3600,
    media_type: WatchableMediaType = WatchableMediaType.EPISODE,
) -> WatchProgress:
    return WatchProgress.create(
        media_id=media_id,
        media_type=media_type,
        position_seconds=position,
        duration_seconds=duration,
    )


@pytest.mark.integration
class TestProgressLookupAdapter:
    """The adapter exposes ProgressSummary without leaking domain types."""

    async def test_find_for_media_ids_returns_summaries(
        self, db_session: AsyncSession
    ) -> None:
        progress_repo = SQLAlchemyWatchProgressRepository(db_session)
        await progress_repo.save(_progress("epi_ser_ABC_1_1", position=900))
        await progress_repo.save(_progress("epi_ser_ABC_1_2", position=3300))

        adapter = ProgressLookupAdapter(progress_repo)

        result = await adapter.find_for_media_ids(
            ["epi_ser_ABC_1_1", "epi_ser_ABC_1_2", "epi_ser_ABC_1_3"],
        )

        assert set(result.keys()) == {"epi_ser_ABC_1_1", "epi_ser_ABC_1_2"}
        assert result["epi_ser_ABC_1_1"].position_seconds == 900
        assert result["epi_ser_ABC_1_1"].percentage == pytest.approx(25.0)
        assert result["epi_ser_ABC_1_2"].status == "completed"

    async def test_find_for_media_ids_with_empty_input(
        self, db_session: AsyncSession
    ) -> None:
        progress_repo = SQLAlchemyWatchProgressRepository(db_session)
        adapter = ProgressLookupAdapter(progress_repo)

        assert await adapter.find_for_media_ids([]) == {}

    async def test_progress_summary_includes_last_watched_at(
        self, db_session: AsyncSession
    ) -> None:
        progress_repo = SQLAlchemyWatchProgressRepository(db_session)
        await progress_repo.save(_progress("epi_ser_ABC_1_1"))

        adapter = ProgressLookupAdapter(progress_repo)
        result = await adapter.find_for_media_ids(["epi_ser_ABC_1_1"])

        summary = result["epi_ser_ABC_1_1"]
        assert summary.last_watched_at is not None
        assert summary.media_id == "epi_ser_ABC_1_1"
