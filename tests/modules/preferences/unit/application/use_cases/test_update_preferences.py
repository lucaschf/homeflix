"""Tests for UpdatePreferencesUseCase."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.preferences.application.dtos.preferences_dtos import UpdatePreferencesInput
from src.modules.preferences.application.use_cases.update_preferences import (
    UpdatePreferencesUseCase,
)
from src.modules.preferences.domain.entities import PlaybackPreferences
from tests.modules.preferences.unit.application.conftest import make_preferences_uow_mock


@pytest.mark.unit
class TestUpdatePreferencesUseCase:
    @pytest.mark.asyncio
    async def test_should_create_defaults_on_first_update(self) -> None:
        mocks = make_preferences_uow_mock()
        mocks.preferences.find_by_user_key.return_value = None
        mocks.preferences.save.side_effect = lambda prefs: prefs
        use_case = UpdatePreferencesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(UpdatePreferencesInput(speed=1.5))

        assert result.speed == 1.5
        # Untouched fields keep the domain defaults.
        assert result.audio_lang == "pt-BR"
        mocks.preferences.save.assert_awaited_once()
        mocks.factory.assert_called_once()
        # UoW was entered and exited exactly once — transaction
        # management lives with the context manager, not with manual
        # commit() calls in the use case.
        mocks.uow.__aenter__.assert_awaited_once()  # type: ignore[attr-defined]
        mocks.uow.__aexit__.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_should_update_existing_entity_without_touching_unset_fields(self) -> None:
        existing = PlaybackPreferences.default_for().apply_updates(
            audio_lang="en-US",
            subtitle_lang="en-US",
        )
        mocks = make_preferences_uow_mock()
        mocks.preferences.find_by_user_key.return_value = existing
        mocks.preferences.save.side_effect = lambda prefs: prefs
        use_case = UpdatePreferencesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(UpdatePreferencesInput(subtitle_mode="always"))

        assert result.subtitle_mode == "always"
        assert result.audio_lang == "en-US"
        assert result.subtitle_lang == "en-US"

    @pytest.mark.asyncio
    async def test_should_reject_invalid_speed(self) -> None:
        mocks = make_preferences_uow_mock()
        mocks.preferences.find_by_user_key.return_value = None
        use_case = UpdatePreferencesUseCase(uow_factory=mocks.factory)

        with pytest.raises(DomainValidationException):
            await use_case.execute(UpdatePreferencesInput(speed=10.0))

        mocks.preferences.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_reject_invalid_quality_value(self) -> None:
        mocks = make_preferences_uow_mock()
        mocks.preferences.find_by_user_key.return_value = None
        use_case = UpdatePreferencesUseCase(uow_factory=mocks.factory)

        with pytest.raises(DomainValidationException):
            await use_case.execute(UpdatePreferencesInput(default_quality="ultra"))

        mocks.preferences.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_reject_invalid_subtitle_mode(self) -> None:
        mocks = make_preferences_uow_mock()
        mocks.preferences.find_by_user_key.return_value = None
        use_case = UpdatePreferencesUseCase(uow_factory=mocks.factory)

        with pytest.raises(DomainValidationException):
            await use_case.execute(UpdatePreferencesInput(subtitle_mode="invalid"))

        mocks.preferences.save.assert_not_awaited()
