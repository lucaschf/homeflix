"""Integration tests for SQLAlchemyWatchProgressRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.infrastructure.persistence.repositories import (
    SQLAlchemyWatchProgressRepository,
)

SAMPLE_MOVIE_ID = "mov_abc123def456"
SAMPLE_EPISODE_ID = "epi_xyz789abc123"
MISSING_MEDIA_ID = "mov_missing00000"


def _create_progress(
    media_id: str = SAMPLE_MOVIE_ID,
    media_type: str = "movie",
    position: int = 1800,
    duration: int = 7200,
) -> WatchProgress:
    return WatchProgress.create(
        media_id=media_id,
        media_type=media_type,
        position_seconds=position,
        duration_seconds=duration,
    )


@pytest.mark.integration
class TestSQLAlchemyWatchProgressRepositorySave:
    """Tests for save (insert + update)."""

    async def test_save_should_insert_new_progress(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        progress = _create_progress()

        saved = await repo.save(progress)

        assert saved.media_id == SAMPLE_MOVIE_ID
        assert saved.position_seconds == 1800
        assert saved.status == "in_progress"

    async def test_save_should_update_existing_progress(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        original = _create_progress(position=1000)
        await repo.save(original)

        updated_entity = original.update_position(position_seconds=3000)
        await repo.save(updated_entity)

        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID)
        assert found is not None
        assert found.position_seconds == 3000

    async def test_save_should_auto_complete_at_90_percent(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        progress = WatchProgress.create(
            media_id=SAMPLE_MOVIE_ID,
            media_type="movie",
            position_seconds=6500,
            duration_seconds=7200,
        )

        saved = await repo.save(progress)

        assert saved.status == "completed"
        assert saved.completed_at is not None


@pytest.mark.integration
class TestSQLAlchemyWatchProgressRepositoryFind:
    """Tests for find operations."""

    async def test_find_by_media_id_should_return_progress(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress())

        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID)

        assert found is not None
        assert found.media_id == SAMPLE_MOVIE_ID

    async def test_find_by_media_id_should_return_none_when_absent(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)

        found = await repo.find_by_media_id(MISSING_MEDIA_ID)

        assert found is None

    async def test_find_by_media_ids_should_return_mapping(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id=SAMPLE_MOVIE_ID))
        await repo.save(
            _create_progress(media_id=SAMPLE_EPISODE_ID, media_type="episode"),
        )

        result = await repo.find_by_media_ids([SAMPLE_MOVIE_ID, SAMPLE_EPISODE_ID])

        assert len(result) == 2
        assert SAMPLE_MOVIE_ID in result
        assert SAMPLE_EPISODE_ID in result

    async def test_find_by_media_ids_should_return_empty_for_empty_input(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)

        result = await repo.find_by_media_ids([])

        assert result == {}

    async def test_find_by_media_ids_should_skip_missing(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id=SAMPLE_MOVIE_ID))

        result = await repo.find_by_media_ids([SAMPLE_MOVIE_ID, MISSING_MEDIA_ID])

        assert list(result.keys()) == [SAMPLE_MOVIE_ID]


@pytest.mark.integration
class TestSQLAlchemyWatchProgressRepositoryList:
    """Tests for list operations."""

    async def test_list_in_progress_should_exclude_completed(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id="mov_aaaaaaaaaaaa"))
        await repo.save(
            WatchProgress.create(
                media_id="mov_bbbbbbbbbbbb",
                media_type="movie",
                position_seconds=7200,
                duration_seconds=7200,
            ),
        )

        result = await repo.list_in_progress()

        assert len(result) == 1
        assert result[0].media_id == "mov_aaaaaaaaaaaa"

    async def test_list_in_progress_should_order_by_last_watched_desc(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        # Save in a specific order; last saved should appear first
        await repo.save(_create_progress(media_id="mov_first0000000"))
        await repo.save(_create_progress(media_id="mov_second000000"))
        await repo.save(_create_progress(media_id="mov_third0000000"))

        result = await repo.list_in_progress()

        assert [p.media_id for p in result] == [
            "mov_third0000000",
            "mov_second000000",
            "mov_first0000000",
        ]

    async def test_list_in_progress_should_respect_limit(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        for i in range(5):
            await repo.save(_create_progress(media_id=f"mov_{i}aaaaaaaaaaa"))

        result = await repo.list_in_progress(limit=2)

        assert len(result) == 2

    async def test_list_recently_watched_should_include_completed(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id="mov_aaaaaaaaaaaa"))
        await repo.save(
            WatchProgress.create(
                media_id="mov_bbbbbbbbbbbb",
                media_type="movie",
                position_seconds=7200,
                duration_seconds=7200,
            ),
        )

        result = await repo.list_recently_watched()

        assert len(result) == 2

    async def test_list_recently_watched_should_exclude_deleted(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id="mov_kept000000000"))
        await repo.save(_create_progress(media_id="mov_deleted000000"))
        await repo.delete("mov_deleted000000")

        result = await repo.list_recently_watched()

        assert len(result) == 1
        assert result[0].media_id == "mov_kept000000000"

    async def test_list_recently_watched_should_respect_limit(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        for i in range(5):
            await repo.save(_create_progress(media_id=f"mov_{i}aaaaaaaaaaa"))

        result = await repo.list_recently_watched(limit=3)

        assert len(result) == 3


@pytest.mark.integration
class TestSQLAlchemyWatchProgressRepositoryDelete:
    """Tests for delete."""

    async def test_delete_should_soft_delete_progress(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress())

        deleted = await repo.delete(SAMPLE_MOVIE_ID)

        assert deleted is True
        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID)
        assert found is None

    async def test_delete_should_return_false_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)

        deleted = await repo.delete(MISSING_MEDIA_ID)

        assert deleted is False

    async def test_delete_should_exclude_from_in_progress_list(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id=SAMPLE_MOVIE_ID))
        await repo.delete(SAMPLE_MOVIE_ID)

        result = await repo.list_in_progress()

        assert result == []
