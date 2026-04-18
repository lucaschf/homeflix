"""Tests for PlaybackPreferences aggregate root."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.preferences.domain.entities import (
    DEFAULT_USER_KEY,
    PlaybackPreferences,
)
from src.modules.preferences.domain.value_objects import Quality, Speed, SubtitleMode


@pytest.mark.unit
class TestDefaultFactory:
    def test_default_for_uses_canonical_values(self) -> None:
        prefs = PlaybackPreferences.default_for()

        assert prefs.user_key == DEFAULT_USER_KEY
        assert prefs.audio_lang == "pt-BR"
        assert prefs.subtitle_lang == "pt-BR"
        assert prefs.subtitle_mode is SubtitleMode.FOREIGN_ONLY
        assert prefs.default_quality is Quality.BEST
        assert prefs.speed == Speed(1.0)
        assert prefs.id is not None
        assert prefs.id.value == "prf_default"

    def test_default_for_custom_user_key(self) -> None:
        prefs = PlaybackPreferences.default_for("alice")
        assert prefs.user_key == "alice"
        assert prefs.id is not None
        assert prefs.id.value == "prf_alice"


@pytest.mark.unit
class TestApplyUpdates:
    def test_should_return_same_instance_when_no_updates_provided(self) -> None:
        prefs = PlaybackPreferences.default_for()
        result = prefs.apply_updates()
        assert result is prefs

    def test_should_update_only_provided_fields(self) -> None:
        prefs = PlaybackPreferences.default_for()

        updated = prefs.apply_updates(speed=1.5, subtitle_mode="always")

        assert updated.speed.value == 1.5
        assert updated.subtitle_mode is SubtitleMode.ALWAYS
        # Untouched fields remain at defaults
        assert updated.audio_lang == "pt-BR"
        assert updated.default_quality is Quality.BEST

    def test_should_coerce_quality_from_string(self) -> None:
        prefs = PlaybackPreferences.default_for()
        updated = prefs.apply_updates(default_quality="1080p")
        assert updated.default_quality is Quality.P1080

    def test_should_reject_invalid_speed(self) -> None:
        prefs = PlaybackPreferences.default_for()
        with pytest.raises(DomainValidationException):
            prefs.apply_updates(speed=10.0)

    def test_should_reject_invalid_subtitle_mode(self) -> None:
        prefs = PlaybackPreferences.default_for()
        with pytest.raises(DomainValidationException):
            prefs.apply_updates(subtitle_mode="invalid")

    def test_should_reject_invalid_quality(self) -> None:
        prefs = PlaybackPreferences.default_for()
        with pytest.raises(DomainValidationException):
            prefs.apply_updates(default_quality="ultra")
