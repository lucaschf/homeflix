"""Tests for PlaybackPreferences aggregate root."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.preferences.domain.entities import PlaybackPreferences
from src.modules.preferences.domain.value_objects import Quality, Speed, SubtitleMode
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")
_OTHER_PROFILE_ID = ProfileId("prf_otherprofile")


@pytest.mark.unit
class TestDefaultFactory:
    def test_default_for_uses_canonical_values(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)

        assert prefs.profile_id == _PROFILE_ID
        assert prefs.audio_lang == "pt-BR"
        assert prefs.subtitle_lang == "pt-BR"
        assert prefs.subtitle_mode is SubtitleMode.FOREIGN_ONLY
        assert prefs.default_quality is Quality.BEST
        assert prefs.speed == Speed(1.0)
        assert prefs.id is not None
        assert prefs.id.value == _PROFILE_ID.value

    def test_default_for_mirrors_arbitrary_profile_id(self) -> None:
        prefs = PlaybackPreferences.default_for(_OTHER_PROFILE_ID)
        assert prefs.profile_id == _OTHER_PROFILE_ID
        assert prefs.id is not None
        assert prefs.id.value == _OTHER_PROFILE_ID.value


@pytest.mark.unit
class TestApplyUpdates:
    def test_should_return_same_instance_when_no_updates_provided(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)
        result = prefs.apply_updates()
        assert result is prefs

    def test_should_update_only_provided_fields(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)

        updated = prefs.apply_updates(speed=1.5, subtitle_mode="always")

        assert updated.speed.value == 1.5
        assert updated.subtitle_mode is SubtitleMode.ALWAYS
        # Untouched fields remain at defaults
        assert updated.audio_lang == "pt-BR"
        assert updated.default_quality is Quality.BEST

    def test_should_coerce_quality_from_string(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)
        updated = prefs.apply_updates(default_quality="1080p")
        assert updated.default_quality is Quality.P1080

    def test_should_reject_invalid_speed(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)
        with pytest.raises(DomainValidationException):
            prefs.apply_updates(speed=10.0)

    def test_should_reject_invalid_subtitle_mode(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)
        with pytest.raises(DomainValidationException):
            prefs.apply_updates(subtitle_mode="invalid")

    def test_should_reject_invalid_quality(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)
        with pytest.raises(DomainValidationException):
            prefs.apply_updates(default_quality="ultra")
