"""Tests for IntroSkipMode enum."""

import pytest

from src.modules.preferences.domain.value_objects import IntroSkipMode


@pytest.mark.unit
class TestIntroSkipMode:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("manual", IntroSkipMode.MANUAL),
            ("auto", IntroSkipMode.AUTO),
            ("autoAfterFirst", IntroSkipMode.AUTO_AFTER_FIRST),
        ],
    )
    def test_should_build_from_canonical_strings(self, raw: str, expected: IntroSkipMode) -> None:
        assert IntroSkipMode(raw) is expected

    def test_should_reject_unknown_value(self) -> None:
        with pytest.raises(ValueError, match="'always'"):
            IntroSkipMode("always")

    def test_should_reject_snake_case_spelling(self) -> None:
        # The wire format is camelCase, matching SubtitleMode's
        # ``foreignOnly`` — a snake_case payload is a client bug, not an
        # alias to be quietly accepted.
        with pytest.raises(ValueError, match="'auto_after_first'"):
            IntroSkipMode("auto_after_first")
