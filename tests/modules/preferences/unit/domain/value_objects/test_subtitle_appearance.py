"""Tests for the SubtitleAppearance value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.preferences.domain.value_objects import (
    CssColor,
    SubtitleAppearance,
    SubtitleFontSize,
)


@pytest.mark.unit
class TestSubtitleAppearance:
    """Construction, defaults, and coercion."""

    def test_default_is_white_on_dim_medium(self) -> None:
        appearance = SubtitleAppearance.default()

        assert appearance.color == CssColor("#FFFFFF")
        assert appearance.background == CssColor("rgba(0, 0, 0, 0.75)")
        assert appearance.font_size is SubtitleFontSize.MEDIUM

    def test_coerces_raw_strings(self) -> None:
        appearance = SubtitleAppearance(
            color="yellow",
            background="#000000",
            font_size="large",
        )

        assert appearance.color.value == "yellow"
        assert appearance.font_size is SubtitleFontSize.LARGE

    def test_rejects_invalid_color(self) -> None:
        with pytest.raises(DomainValidationException):
            SubtitleAppearance(color="#GGG", background="#000000", font_size="small")

    def test_rejects_unknown_font_size(self) -> None:
        with pytest.raises((DomainValidationException, ValueError)):
            SubtitleAppearance(color="#FFFFFF", background="#000000", font_size="huge")

    def test_equality_by_value(self) -> None:
        a = SubtitleAppearance(color="#FFFFFF", background="#000000", font_size="medium")
        b = SubtitleAppearance(color="#FFFFFF", background="#000000", font_size="medium")
        assert a == b
