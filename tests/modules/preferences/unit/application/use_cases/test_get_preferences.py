"""Tests for GetPreferencesUseCase."""

import pytest

from src.modules.preferences.application.dtos.preferences_dtos import GetPreferencesInput
from src.modules.preferences.application.use_cases.get_preferences import (
    GetPreferencesUseCase,
)
from src.modules.preferences.domain.entities import PlaybackPreferences
from src.modules.preferences.domain.value_objects import (
    CreditsSkipMode,
    IntroSkipMode,
    Quality,
    Speed,
    SubtitleMode,
)
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.preferences.unit.application.conftest import make_preferences_uow_mock

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestGetPreferencesUseCase:
    @pytest.mark.asyncio
    async def test_should_return_defaults_when_no_row_exists(self) -> None:
        mocks = make_preferences_uow_mock()
        mocks.preferences.find_by_profile_id.return_value = None
        use_case = GetPreferencesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(GetPreferencesInput(profile_id=_PROFILE_ID.value))

        assert result.audio_lang == "pt-BR"
        assert result.subtitle_lang == "pt-BR"
        assert result.subtitle_mode == "foreignOnly"
        assert result.default_quality == "best"
        assert result.speed == 1.0
        assert result.intro_skip_mode == "manual"
        assert result.credits_skip_mode == "manual"
        mocks.preferences.find_by_profile_id.assert_awaited_once_with(_PROFILE_ID)

    @pytest.mark.asyncio
    async def test_should_project_persisted_entity(self) -> None:
        mocks = make_preferences_uow_mock()
        mocks.preferences.find_by_profile_id.return_value = PlaybackPreferences.default_for(
            _PROFILE_ID
        ).apply_updates(
            subtitle_mode="always",
            default_quality="1080p",
            speed=1.5,
            intro_skip_mode="autoAfterFirst",
            credits_skip_mode="auto",
        )
        use_case = GetPreferencesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(GetPreferencesInput(profile_id=_PROFILE_ID.value))

        assert result.subtitle_mode == SubtitleMode.ALWAYS.value
        assert result.default_quality == Quality.P1080.value
        assert result.speed == 1.5
        assert result.speed == Speed(1.5).value
        assert result.intro_skip_mode == IntroSkipMode.AUTO_AFTER_FIRST.value
        assert result.credits_skip_mode == CreditsSkipMode.AUTO.value
