"""Tests for SubtitleMode enumeration."""

from src.domain.library.value_objects.subtitle_mode import SubtitleMode


class TestSubtitleMode:
    """Tests for SubtitleMode enum."""

    def test_should_have_always_mode(self):
        assert SubtitleMode.ALWAYS.value == "always"

    def test_should_have_foreign_audio_only_mode(self):
        assert SubtitleMode.FOREIGN_AUDIO_ONLY.value == "foreign"

    def test_should_have_forced_only_mode(self):
        assert SubtitleMode.FORCED_ONLY.value == "forced"

    def test_should_have_none_mode(self):
        assert SubtitleMode.NONE.value == "none"

    def test_should_create_from_string(self):
        mode = SubtitleMode("always")

        assert mode == SubtitleMode.ALWAYS

    def test_should_have_four_modes(self):
        assert len(SubtitleMode) == 4
