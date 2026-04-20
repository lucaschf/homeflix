"""Tests for GetPreferencesUseCase."""

import pytest

from src.modules.preferences.application.use_cases.get_preferences import (
    GetPreferencesUseCase,
)
from src.modules.preferences.domain.entities import DEFAULT_USER_KEY, PlaybackPreferences
from src.modules.preferences.domain.value_objects import Quality, Speed, SubtitleMode
from tests.modules.preferences.unit.application.conftest import make_preferences_uow_mock


@pytest.mark.unit
class TestGetPreferencesUseCase:
    @pytest.mark.asyncio
    async def test_should_return_defaults_when_no_row_exists(self) -> None:
        mocks = make_preferences_uow_mock()
        mocks.preferences.find_by_user_key.return_value = None
        use_case = GetPreferencesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute()

        assert result.audio_lang == "pt-BR"
        assert result.subtitle_lang == "pt-BR"
        assert result.subtitle_mode == "foreignOnly"
        assert result.default_quality == "best"
        assert result.speed == 1.0
        mocks.preferences.find_by_user_key.assert_awaited_once_with(DEFAULT_USER_KEY)

    @pytest.mark.asyncio
    async def test_should_project_persisted_entity(self) -> None:
        mocks = make_preferences_uow_mock()
        mocks.preferences.find_by_user_key.return_value = (
            PlaybackPreferences.default_for().apply_updates(
                subtitle_mode="always",
                default_quality="1080p",
                speed=1.5,
            )
        )
        use_case = GetPreferencesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute()

        assert result.subtitle_mode == SubtitleMode.ALWAYS.value
        assert result.default_quality == Quality.P1080.value
        assert result.speed == 1.5
        assert result.speed == Speed(1.5).value
