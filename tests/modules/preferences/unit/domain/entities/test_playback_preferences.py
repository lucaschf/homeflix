"""Tests for PlaybackPreferences aggregate root."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.preferences.domain.entities import PlaybackPreferences
from src.modules.preferences.domain.value_objects import (
    CreditsSkipMode,
    IntroSkipMode,
    Quality,
    Speed,
    SubtitleMode,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")
_OTHER_PROFILE_ID = ProfileId("prf_otherprofile")


@pytest.mark.unit
class TestDefaultFactory:
    def test_default_for_uses_canonical_values(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)

        assert prefs.profile_id == _PROFILE_ID
        assert prefs.audio_lang.value == "pt-BR"
        assert prefs.subtitle_lang.value == "pt-BR"
        assert prefs.subtitle_mode is SubtitleMode.FOREIGN_ONLY
        assert prefs.default_quality is Quality.BEST
        assert prefs.speed == Speed(1.0)
        assert prefs.subtitle_appearance.color.value == "#FFFFFF"
        assert prefs.subtitle_appearance.background.value == "rgba(0, 0, 0, 0.75)"
        assert prefs.subtitle_appearance.font_size.value == "medium"
        assert prefs.subtitle_appearance.text_edge.value == "shadow"
        # Default is today's behaviour — a button, never an unasked seek.
        assert prefs.intro_skip_mode is IntroSkipMode.MANUAL
        assert prefs.credits_skip_mode is CreditsSkipMode.MANUAL
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
        assert updated.audio_lang.value == "pt-BR"
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

    def test_should_reject_garbage_audio_lang(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)
        with pytest.raises(DomainValidationException):
            prefs.apply_updates(audio_lang="portugues")

    def test_should_normalize_language_tag(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)
        updated = prefs.apply_updates(audio_lang="en-us", subtitle_lang="PT-br")
        assert updated.audio_lang.value == "en-US"
        assert updated.subtitle_lang.value == "pt-BR"


@pytest.mark.unit
class TestSubtitleAppearanceUpdates:
    def test_partial_merge_keeps_untouched_knobs(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)

        updated = prefs.apply_updates(subtitle_appearance={"color": "yellow"})

        # Only color changed; background, size, and edge keep their defaults.
        assert updated.subtitle_appearance.color.value == "yellow"
        assert updated.subtitle_appearance.background.value == "rgba(0, 0, 0, 0.75)"
        assert updated.subtitle_appearance.font_size.value == "medium"
        assert updated.subtitle_appearance.text_edge.value == "shadow"
        # Immutable per ADR-007 — the original is untouched.
        assert prefs.subtitle_appearance.color.value == "#FFFFFF"

    def test_full_replace(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)

        updated = prefs.apply_updates(
            subtitle_appearance={
                "color": "#00FF00",
                "background": "rgba(0, 0, 0, 0.5)",
                "font_size": "large",
                "text_edge": "outline",
            },
        )

        assert updated.subtitle_appearance.color.value == "#00FF00"
        assert updated.subtitle_appearance.font_size.value == "large"
        assert updated.subtitle_appearance.text_edge.value == "outline"

    def test_rejects_invalid_color(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)
        with pytest.raises(DomainValidationException):
            prefs.apply_updates(subtitle_appearance={"color": "#GG0000"})


@pytest.mark.unit
class TestSkipModeUpdates:
    def test_should_coerce_intro_skip_mode_from_string(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)

        updated = prefs.apply_updates(intro_skip_mode="autoAfterFirst")

        assert updated.intro_skip_mode is IntroSkipMode.AUTO_AFTER_FIRST
        # Credits are an independent knob — turning one on leaves the
        # other where it was.
        assert updated.credits_skip_mode is CreditsSkipMode.MANUAL
        # Immutable per ADR-007 — the original is untouched.
        assert prefs.intro_skip_mode is IntroSkipMode.MANUAL

    def test_should_coerce_credits_skip_mode_from_string(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)

        updated = prefs.apply_updates(credits_skip_mode="auto")

        assert updated.credits_skip_mode is CreditsSkipMode.AUTO
        assert updated.intro_skip_mode is IntroSkipMode.MANUAL

    def test_should_update_both_modes_at_once(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)

        updated = prefs.apply_updates(intro_skip_mode="auto", credits_skip_mode="auto")

        assert updated.intro_skip_mode is IntroSkipMode.AUTO
        assert updated.credits_skip_mode is CreditsSkipMode.AUTO

    def test_should_accept_enum_members_alongside_strings(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)

        updated = prefs.apply_updates(intro_skip_mode=IntroSkipMode.AUTO)

        assert updated.intro_skip_mode is IntroSkipMode.AUTO

    def test_should_reject_invalid_intro_skip_mode(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)
        with pytest.raises(DomainValidationException):
            prefs.apply_updates(intro_skip_mode="always")

    def test_should_reject_intro_only_mode_on_credits(self) -> None:
        prefs = PlaybackPreferences.default_for(_PROFILE_ID)
        with pytest.raises(DomainValidationException):
            prefs.apply_updates(credits_skip_mode="autoAfterFirst")
