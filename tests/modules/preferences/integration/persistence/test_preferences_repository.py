"""Integration tests for SQLAlchemyPreferencesRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.preferences.domain.entities import PlaybackPreferences
from src.modules.preferences.domain.value_objects import Quality, SubtitleMode
from src.modules.preferences.infrastructure.persistence.repositories import (
    SQLAlchemyPreferencesRepository,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")
_OTHER_PROFILE_ID = ProfileId("prf_otherprofile")


@pytest.mark.integration
class TestSQLAlchemyPreferencesRepository:
    async def test_find_by_profile_id_returns_none_on_empty_table(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyPreferencesRepository(db_session)
        assert await repo.find_by_profile_id(_PROFILE_ID) is None

    async def test_save_persists_new_row(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyPreferencesRepository(db_session)
        prefs = PlaybackPreferences.default_for(_PROFILE_ID).apply_updates(
            subtitle_mode="always",
            speed=1.25,
        )

        saved = await repo.save(prefs)

        assert saved.profile_id == _PROFILE_ID
        assert saved.subtitle_mode is SubtitleMode.ALWAYS
        assert saved.speed.value == 1.25
        assert saved.created_at is not None

        found = await repo.find_by_profile_id(_PROFILE_ID)
        assert found is not None
        assert found.subtitle_mode is SubtitleMode.ALWAYS
        assert found.speed.value == 1.25

    async def test_save_updates_existing_row_without_duplicating(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyPreferencesRepository(db_session)
        await repo.save(PlaybackPreferences.default_for(_PROFILE_ID))

        existing = await repo.find_by_profile_id(_PROFILE_ID)
        assert existing is not None
        updated = existing.apply_updates(default_quality="1080p")

        saved = await repo.save(updated)

        assert saved.default_quality is Quality.P1080
        # Still just one row — second find resolves to the same record.
        second = await repo.find_by_profile_id(_PROFILE_ID)
        assert second is not None
        assert second.default_quality is Quality.P1080

    async def test_find_by_profile_id_isolates_across_profiles(
        self, db_session: AsyncSession
    ) -> None:
        # Two profiles, each with their own preferences row: each lookup
        # must see only its own row. The DB unique on ``profile_id`` plus
        # the explicit WHERE filter guarantee no cross-profile leakage.
        repo = SQLAlchemyPreferencesRepository(db_session)
        await repo.save(
            PlaybackPreferences.default_for(_PROFILE_ID).apply_updates(speed=1.5),
        )
        await repo.save(
            PlaybackPreferences.default_for(_OTHER_PROFILE_ID).apply_updates(speed=0.75),
        )

        first = await repo.find_by_profile_id(_PROFILE_ID)
        other = await repo.find_by_profile_id(_OTHER_PROFILE_ID)

        assert first is not None
        assert other is not None
        assert first.profile_id == _PROFILE_ID
        assert other.profile_id == _OTHER_PROFILE_ID
        assert first.speed.value == 1.5
        assert other.speed.value == 0.75
