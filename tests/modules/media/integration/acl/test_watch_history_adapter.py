"""Integration tests for the Media WatchHistoryAdapter."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.infrastructure.acl import WatchHistoryAdapter
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
_OTHER_PROFILE_ID = ProfileId("prf_otherprofile")


def _progress(
    media_id: str,
    position: int = 1800,
    duration: int = 3600,
    *,
    profile_id: ProfileId = _PROFILE_ID,
) -> WatchProgress:
    media_type = (
        WatchableMediaType.MOVIE if media_id.startswith("mov_") else WatchableMediaType.EPISODE
    )
    return WatchProgress.create(
        profile_id=profile_id,
        media_id=media_id,
        media_type=media_type,
        position_seconds=position,
        duration_seconds=duration,
    )


def _make_adapter(
    session_factory: async_sessionmaker[AsyncSession],
) -> WatchHistoryAdapter:
    return WatchHistoryAdapter(
        SqlAlchemyWatchProgressUnitOfWorkFactory(session_factory),
    )


@pytest.mark.integration
class TestWatchHistoryAdapter:
    """The adapter collapses progress rows into distinct movie/series titles."""

    async def test_collapses_episodes_into_their_series_and_keeps_movies(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        progress_repo = SQLAlchemyWatchProgressRepository(db_session)
        # Oldest first so the series' most recent row is episode 1x3.
        await progress_repo.save(_progress("epi_ser_abc123def456_1_1", position=3300))
        await progress_repo.save(_progress("epi_ser_abc123def456_1_2", position=3300))
        await progress_repo.save(_progress("mov_abc123def456", position=900))
        await progress_repo.save(_progress("epi_ser_abc123def456_1_3", position=600))
        await db_session.commit()

        adapter = _make_adapter(session_factory)

        result = await adapter.list_recently_watched(_PROFILE_ID.value, limit=10)

        assert [(t.media_id, t.media_type) for t in result] == [
            ("ser_abc123def456", "series"),
            ("mov_abc123def456", "movie"),
        ]
        series, movie = result
        # Status/timestamp come from the most recent row of the title.
        assert series.status == "in_progress"
        assert movie.status == "in_progress"
        assert series.last_watched_at >= movie.last_watched_at

    async def test_reports_completed_status_for_finished_movies(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        progress_repo = SQLAlchemyWatchProgressRepository(db_session)
        await progress_repo.save(_progress("mov_abc123def456", position=3500))
        await db_session.commit()

        adapter = _make_adapter(session_factory)

        result = await adapter.list_recently_watched(_PROFILE_ID.value, limit=10)

        assert len(result) == 1
        assert result[0].status == "completed"

    async def test_respects_title_limit_after_collapsing(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        progress_repo = SQLAlchemyWatchProgressRepository(db_session)
        for episode in range(1, 6):
            await progress_repo.save(_progress(f"epi_ser_abc123def456_1_{episode}"))
        await progress_repo.save(_progress("mov_abc123def456"))
        await progress_repo.save(_progress("mov_xyz123def456"))
        await db_session.commit()

        adapter = _make_adapter(session_factory)

        result = await adapter.list_recently_watched(_PROFILE_ID.value, limit=2)

        # The two most recent titles are the movies; five episode rows
        # of the older series don't crowd them out or count as five.
        assert [t.media_id for t in result] == ["mov_xyz123def456", "mov_abc123def456"]

    async def test_isolates_across_profiles(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        progress_repo = SQLAlchemyWatchProgressRepository(db_session)
        await progress_repo.save(_progress("mov_abc123def456"))
        await progress_repo.save(_progress("mov_xyz123def456", profile_id=_OTHER_PROFILE_ID))
        await db_session.commit()

        adapter = _make_adapter(session_factory)

        mine = await adapter.list_recently_watched(_PROFILE_ID.value, limit=10)
        theirs = await adapter.list_recently_watched(_OTHER_PROFILE_ID.value, limit=10)

        assert [t.media_id for t in mine] == ["mov_abc123def456"]
        assert [t.media_id for t in theirs] == ["mov_xyz123def456"]

    async def test_empty_history_and_non_positive_limit(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        adapter = _make_adapter(session_factory)

        assert await adapter.list_recently_watched(_PROFILE_ID.value, limit=10) == []
        assert await adapter.list_recently_watched(_PROFILE_ID.value, limit=0) == []
