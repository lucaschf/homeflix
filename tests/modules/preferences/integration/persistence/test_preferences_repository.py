"""Integration tests for SQLAlchemyPreferencesRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.preferences.domain.entities import (
    DEFAULT_USER_KEY,
    PlaybackPreferences,
)
from src.modules.preferences.domain.value_objects import Quality, SubtitleMode
from src.modules.preferences.infrastructure.persistence.repositories import (
    SQLAlchemyPreferencesRepository,
)


@pytest.mark.integration
class TestSQLAlchemyPreferencesRepository:
    async def test_find_by_user_key_returns_none_on_empty_table(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyPreferencesRepository(db_session)
        assert await repo.find_by_user_key(DEFAULT_USER_KEY) is None

    async def test_save_persists_new_row(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyPreferencesRepository(db_session)
        prefs = PlaybackPreferences.default_for().apply_updates(
            subtitle_mode="always",
            speed=1.25,
        )

        saved = await repo.save(prefs)

        assert saved.user_key == DEFAULT_USER_KEY
        assert saved.subtitle_mode is SubtitleMode.ALWAYS
        assert saved.speed.value == 1.25
        assert saved.created_at is not None

        found = await repo.find_by_user_key(DEFAULT_USER_KEY)
        assert found is not None
        assert found.subtitle_mode is SubtitleMode.ALWAYS
        assert found.speed.value == 1.25

    async def test_save_updates_existing_row_without_duplicating(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyPreferencesRepository(db_session)
        await repo.save(PlaybackPreferences.default_for())

        existing = await repo.find_by_user_key(DEFAULT_USER_KEY)
        assert existing is not None
        updated = existing.apply_updates(default_quality="1080p")

        saved = await repo.save(updated)

        assert saved.default_quality is Quality.P1080
        # Still just one row — second find resolves to the same record.
        second = await repo.find_by_user_key(DEFAULT_USER_KEY)
        assert second is not None
        assert second.default_quality is Quality.P1080
