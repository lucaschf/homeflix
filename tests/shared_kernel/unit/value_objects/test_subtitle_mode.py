"""Tests for SubtitleMode enum."""

import pytest

from src.shared_kernel.value_objects.subtitle_mode import SubtitleMode


@pytest.mark.unit
class TestSubtitleMode:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("off", SubtitleMode.OFF),
            ("foreignOnly", SubtitleMode.FOREIGN_ONLY),
            ("always", SubtitleMode.ALWAYS),
            ("forcedOnly", SubtitleMode.FORCED_ONLY),
        ],
    )
    def test_should_build_from_canonical_strings(self, raw: str, expected: SubtitleMode) -> None:
        assert SubtitleMode(raw) is expected

    def test_should_reject_unknown_value(self) -> None:
        with pytest.raises(ValueError, match="'bogus'"):
            SubtitleMode("bogus")

    def test_string_value_is_canonical(self) -> None:
        assert SubtitleMode.FOREIGN_ONLY.value == "foreignOnly"
