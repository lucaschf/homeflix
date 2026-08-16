"""Tests for the CssColor value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.preferences.domain.value_objects import CssColor


@pytest.mark.unit
class TestCssColorValid:
    """Accepted CSS color forms."""

    @pytest.mark.parametrize(
        "value",
        [
            "#FFF",
            "#FFFF",
            "#FFFFFF",
            "#FFFFFF80",
            "#1a2b3c",
            "rgba(0, 0, 0, 0.75)",
            "rgb(255,255,255)",
            "hsl(120, 50%, 50%)",
            "yellow",
            "white",
        ],
    )
    def test_accepts(self, value: str) -> None:
        assert CssColor(value).value == value

    def test_trims_whitespace(self) -> None:
        assert CssColor("  #FFFFFF  ").value == "#FFFFFF"


@pytest.mark.unit
class TestCssColorInvalid:
    """Rejected values raise a domain validation error."""

    @pytest.mark.parametrize(
        "value",
        [
            "#GG0000",  # non-hex digits
            "#FF",  # too short
            "#FFFFF",  # 5 digits
            "not a color!",  # punctuation
            "rgb[0,0,0]",  # wrong brackets
            "",  # empty
        ],
    )
    def test_rejects(self, value: str) -> None:
        with pytest.raises(DomainValidationException):
            CssColor(value)
