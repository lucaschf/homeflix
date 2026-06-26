"""Integration tests for the Collections ProgressLookupAdapter."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.collections.infrastructure.acl import ProgressLookupAdapter
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


def _movie_progress(
    media_id: str,
    position: int = 1800,
    duration: int = 3600,
    *,
    profile_id: ProfileId = _PROFILE_ID,
) -> WatchProgress:
    return WatchProgress.create(
        profile_id=profile_id,
        media_id=media_id,
        media_type=WatchableMediaType.MOVIE,
        position_seconds=position,
        duration_seconds=duration,
    )


def _make_adapter(session_factory: async_sessionmaker[AsyncSession]) -> ProgressLookupAdapter:
    return ProgressLookupAdapter(SqlAlchemyWatchProgressUnitOfWorkFactory(session_factory))


@pytest.mark.integration
class TestCollectionsProgressLookupAdapter:
    """The adapter exposes watched fractions for the Collections BC."""

    async def test_get_progress_returns_fraction_for_caller_profile(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_movie_progress("mov_abc123def456", position=900, duration=3600))
        await db_session.commit()

        adapter = _make_adapter(session_factory)

        result = await adapter.get_progress(
            ["mov_abc123def456", "mov_missing00000"],
            profile_id=_PROFILE_ID.value,
        )

        # 900 / 3600 = 0.25; unknown id is simply absent.
        assert result == {"mov_abc123def456": pytest.approx(0.25)}

    async def test_get_progress_with_empty_input(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        adapter = _make_adapter(session_factory)

        assert await adapter.get_progress([], profile_id=_PROFILE_ID.value) == {}

    async def test_get_progress_isolates_across_profiles(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_movie_progress("mov_abc123def456", position=900))
        await repo.save(
            _movie_progress("mov_abc123def456", position=3600, profile_id=_OTHER_PROFILE_ID),
        )
        await db_session.commit()

        adapter = _make_adapter(session_factory)

        mine = await adapter.get_progress(["mov_abc123def456"], profile_id=_PROFILE_ID.value)
        theirs = await adapter.get_progress(
            ["mov_abc123def456"], profile_id=_OTHER_PROFILE_ID.value
        )

        assert mine["mov_abc123def456"] == pytest.approx(0.25)
        assert theirs["mov_abc123def456"] == pytest.approx(1.0)
