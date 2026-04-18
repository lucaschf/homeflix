"""Tests for Quality enum."""

import pytest

from src.modules.preferences.domain.value_objects import Quality


@pytest.mark.unit
class TestQuality:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("auto", Quality.AUTO),
            ("best", Quality.BEST),
            ("1080p", Quality.P1080),
            ("720p", Quality.P720),
            ("480p", Quality.P480),
            ("360p", Quality.P360),
        ],
    )
    def test_should_build_from_canonical_strings(self, raw: str, expected: Quality) -> None:
        assert Quality(raw) is expected

    def test_should_reject_unknown_value(self) -> None:
        with pytest.raises(ValueError, match="'2160p'"):
            Quality("2160p")
