"""Integration tests for SQLAlchemyWatchProgressRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import (
    WatchableMediaId,
    WatchableMediaType,
)
from src.modules.watch_progress.infrastructure.persistence.repositories import (
    SQLAlchemyWatchProgressRepository,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

SAMPLE_MOVIE_ID = WatchableMediaId("mov_abc123def456")
SAMPLE_EPISODE_ID = WatchableMediaId("epi_ser_xyz789abc123_1_2")
MISSING_MEDIA_ID = WatchableMediaId("mov_missing00000")
_PROFILE_ID = ProfileId("prf_test12345678")


def _create_progress(
    media_id: WatchableMediaId | str = SAMPLE_MOVIE_ID,
    media_type: WatchableMediaType = WatchableMediaType.MOVIE,
    position: int = 1800,
    duration: int = 7200,
    profile_id: ProfileId = _PROFILE_ID,
) -> WatchProgress:
    return WatchProgress.create(
        profile_id=profile_id,
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
        assert saved.profile_id == _PROFILE_ID

    async def test_save_should_update_existing_progress(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        original = _create_progress(position=1000)
        await repo.save(original)

        updated_entity = original.update_position(position_seconds=3000)
        await repo.save(updated_entity)

        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)
        assert found is not None
        assert found.position_seconds == 3000

    async def test_save_should_restore_and_update_soft_deleted_row(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        original = _create_progress(position=500)
        await repo.save(original)
        await repo.delete(SAMPLE_MOVIE_ID, _PROFILE_ID)

        resumed = _create_progress(position=750)
        await repo.save(resumed)

        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)
        assert found is not None
        assert found.position_seconds == 750

    async def test_save_should_auto_complete_at_90_percent(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        progress = WatchProgress.create(
            profile_id=_PROFILE_ID,
            media_id=SAMPLE_MOVIE_ID,
            media_type=WatchableMediaType.MOVIE,
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

        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert found is not None
        assert found.media_id == SAMPLE_MOVIE_ID

    async def test_find_by_media_id_should_return_none_when_absent(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)

        found = await repo.find_by_media_id(MISSING_MEDIA_ID, _PROFILE_ID)

        assert found is None

    async def test_find_by_media_id_should_isolate_by_profile(
        self, db_session: AsyncSession
    ) -> None:
        # Two profiles, same media: each sees only their own row.
        other_profile = ProfileId("prf_otherprofile")
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(position=100))
        await repo.save(_create_progress(position=500, profile_id=other_profile))

        first = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)
        other = await repo.find_by_media_id(SAMPLE_MOVIE_ID, other_profile)

        assert first is not None
        assert other is not None
        assert first.position_seconds == 100
        assert other.position_seconds == 500

    async def test_find_by_media_ids_should_return_mapping(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id=SAMPLE_MOVIE_ID))
        await repo.save(
            _create_progress(media_id=SAMPLE_EPISODE_ID, media_type=WatchableMediaType.EPISODE),
        )

        result = await repo.find_by_media_ids([SAMPLE_MOVIE_ID, SAMPLE_EPISODE_ID], _PROFILE_ID)

        assert len(result) == 2
        assert SAMPLE_MOVIE_ID.value in result
        assert SAMPLE_EPISODE_ID.value in result

    async def test_find_by_media_ids_should_return_empty_for_empty_input(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)

        result = await repo.find_by_media_ids([], _PROFILE_ID)

        assert result == {}

    async def test_find_by_media_ids_should_skip_missing(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id=SAMPLE_MOVIE_ID))

        result = await repo.find_by_media_ids([SAMPLE_MOVIE_ID, MISSING_MEDIA_ID], _PROFILE_ID)

        assert list(result.keys()) == [SAMPLE_MOVIE_ID.value]


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
                profile_id=_PROFILE_ID,
                media_id="mov_bbbbbbbbbbbb",
                media_type=WatchableMediaType.MOVIE,
                position_seconds=7200,
                duration_seconds=7200,
            ),
        )

        result = await repo.list_in_progress(_PROFILE_ID)

        assert len(result) == 1
        assert result[0].media_id.value == "mov_aaaaaaaaaaaa"

    async def test_list_in_progress_should_order_by_last_watched_desc(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id="mov_first0000000"))
        await repo.save(_create_progress(media_id="mov_second000000"))
        await repo.save(_create_progress(media_id="mov_third0000000"))

        result = await repo.list_in_progress(_PROFILE_ID)

        assert [p.media_id.value for p in result] == [
            "mov_third0000000",
            "mov_second000000",
            "mov_first0000000",
        ]

    async def test_list_in_progress_should_respect_limit(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        for i in range(5):
            await repo.save(_create_progress(media_id=f"mov_{i}aaaaaaaaaaa"))

        result = await repo.list_in_progress(_PROFILE_ID, limit=2)

        assert len(result) == 2

    async def test_list_in_progress_should_isolate_by_profile(
        self, db_session: AsyncSession
    ) -> None:
        other_profile = ProfileId("prf_otherprofile")
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id="mov_aaaaaaaaaaaa"))
        await repo.save(_create_progress(media_id="mov_bbbbbbbbbbbb", profile_id=other_profile))

        first_view = await repo.list_in_progress(_PROFILE_ID)
        other_view = await repo.list_in_progress(other_profile)

        assert {p.media_id.value for p in first_view} == {"mov_aaaaaaaaaaaa"}
        assert {p.media_id.value for p in other_view} == {"mov_bbbbbbbbbbbb"}

    async def test_list_recently_watched_should_include_completed(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id="mov_aaaaaaaaaaaa"))
        await repo.save(
            WatchProgress.create(
                profile_id=_PROFILE_ID,
                media_id="mov_bbbbbbbbbbbb",
                media_type=WatchableMediaType.MOVIE,
                position_seconds=7200,
                duration_seconds=7200,
            ),
        )

        result = await repo.list_recently_watched(_PROFILE_ID)

        assert len(result) == 2

    async def test_list_recently_watched_should_exclude_deleted(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id="mov_kept00000000"))
        await repo.save(_create_progress(media_id="mov_deleted00000"))
        await repo.delete(WatchableMediaId("mov_deleted00000"), _PROFILE_ID)

        result = await repo.list_recently_watched(_PROFILE_ID)

        assert len(result) == 1
        assert result[0].media_id.value == "mov_kept00000000"

    async def test_list_recently_watched_should_respect_limit(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        for i in range(5):
            await repo.save(_create_progress(media_id=f"mov_{i}aaaaaaaaaaa"))

        result = await repo.list_recently_watched(_PROFILE_ID, limit=3)

        assert len(result) == 3


@pytest.mark.integration
class TestSQLAlchemyWatchProgressRepositoryDelete:
    """Tests for delete."""

    async def test_delete_should_soft_delete_progress(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress())

        deleted = await repo.delete(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert deleted is True
        found = await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)
        assert found is None

    async def test_delete_should_return_false_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)

        deleted = await repo.delete(MISSING_MEDIA_ID, _PROFILE_ID)

        assert deleted is False

    async def test_delete_should_not_remove_other_profiles_row(
        self, db_session: AsyncSession
    ) -> None:
        # Per-profile delete must not affect another profile's row for the
        # same media — the unique constraint is composite, but the WHERE
        # clause must filter explicitly too.
        other_profile = ProfileId("prf_otherprofile")
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress())
        await repo.save(_create_progress(profile_id=other_profile))

        await repo.delete(SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert (await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)) is None
        assert (await repo.find_by_media_id(SAMPLE_MOVIE_ID, other_profile)) is not None

    async def test_delete_should_exclude_from_in_progress_list(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress(media_id=SAMPLE_MOVIE_ID))
        await repo.delete(SAMPLE_MOVIE_ID, _PROFILE_ID)

        result = await repo.list_in_progress(_PROFILE_ID)

        assert result == []


@pytest.mark.integration
class TestDeleteAllForMovie:
    """Tests for ``delete_all_for_movie`` — driven by the cross-BC
    promote-to-series handler."""

    async def test_should_clear_every_profile_row_for_the_movie(
        self, db_session: AsyncSession
    ) -> None:
        other_profile = ProfileId("prf_otherprofile")
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress())
        await repo.save(_create_progress(profile_id=other_profile))

        deleted = await repo.delete_all_for_movie(SAMPLE_MOVIE_ID.as_movie_id())

        assert deleted == 2
        assert (await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)) is None
        assert (await repo.find_by_media_id(SAMPLE_MOVIE_ID, other_profile)) is None

    async def test_should_return_zero_when_nothing_matches(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)

        deleted = await repo.delete_all_for_movie(MISSING_MEDIA_ID.as_movie_id())

        assert deleted == 0


@pytest.mark.integration
class TestDeleteAllForProfiles:
    """Tests for ``delete_all_for_profiles`` — driven by the cross-BC user-delete handler."""

    async def test_should_clear_every_row_for_each_listed_profile(
        self, db_session: AsyncSession
    ) -> None:
        other_profile = ProfileId("prf_otherprofile")
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress())
        await repo.save(_create_progress(profile_id=other_profile))

        deleted = await repo.delete_all_for_profiles(
            [_PROFILE_ID.value, other_profile.value],
        )

        assert deleted == 2
        assert (await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)) is None
        assert (await repo.find_by_media_id(SAMPLE_MOVIE_ID, other_profile)) is None

    async def test_should_leave_unlisted_profiles_alone(self, db_session: AsyncSession) -> None:
        kept_profile = ProfileId("prf_keptprofile1")
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress())
        await repo.save(_create_progress(profile_id=kept_profile))

        deleted = await repo.delete_all_for_profiles([_PROFILE_ID.value])

        assert deleted == 1
        assert (await repo.find_by_media_id(SAMPLE_MOVIE_ID, kept_profile)) is not None

    async def test_should_be_noop_for_empty_profile_list(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress())

        deleted = await repo.delete_all_for_profiles([])

        assert deleted == 0
        assert (await repo.find_by_media_id(SAMPLE_MOVIE_ID, _PROFILE_ID)) is not None


@pytest.mark.integration
class TestListDropsCorruptRows:
    """Rows persisted before media-id validation may carry garbage ids;
    list reads drop them with a WARNING instead of failing the request."""

    async def test_list_recently_watched_drops_invalid_media_id_row(
        self,
        db_session: AsyncSession,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import logging
        from datetime import UTC, datetime

        from src.modules.watch_progress.infrastructure.persistence.models import (
            WatchProgressModel,
        )

        repo = SQLAlchemyWatchProgressRepository(db_session)
        await repo.save(_create_progress())
        db_session.add(
            WatchProgressModel(
                external_id="prg_corrupt00000",
                profile_id=_PROFILE_ID.value,
                media_id="epi_garbage",
                media_type="episode",
                position_seconds=10,
                duration_seconds=100,
                status="in_progress",
                last_watched_at=datetime.now(UTC),
            ),
        )
        await db_session.flush()

        with caplog.at_level(logging.WARNING):
            result = await repo.list_recently_watched(_PROFILE_ID)

        assert [p.media_id for p in result] == [SAMPLE_MOVIE_ID]
        assert any("invalid media_id" in record.message for record in caplog.records)
