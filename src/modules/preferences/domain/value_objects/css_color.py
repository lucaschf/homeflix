"""CSS color value object for subtitle appearance."""

import re
from typing import Any

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject
from src.modules.preferences.domain.rule_codes import PreferencesRuleCodes

_HEX_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_FUNC_PATTERN = re.compile(r"^(?:rgb|rgba|hsl|hsla)\([0-9.,%\s/]+\)$")
_NAME_PATTERN = re.compile(r"^[a-zA-Z]{1,40}$")


class CssColor(StringValueObject):
    """A CSS color the player can apply to subtitle text or background.

    Accepts the color forms a browser understands and that the subtitle
    overlay renders directly: hex (``#RGB`` / ``#RGBA`` / ``#RRGGBB`` /
    ``#RRGGBBAA``), functional notation (``rgb()`` / ``rgba()`` / ``hsl()``
    / ``hsla()``), and bare CSS color names (``yellow``). Validated once
    here so an invalid value can never reach the client stylesheet.

    Example:
        >>> CssColor("#FFFFFF").value
        '#FFFFFF'
        >>> CssColor("rgba(0, 0, 0, 0.75)").value
        'rgba(0, 0, 0, 0.75)'
    """

    @model_validator(mode="before")
    @classmethod
    def validate_color(cls, value: Any) -> str:
        """Validate that value is a hex, functional, or named CSS color."""
        if not isinstance(value, str):
            raise ValueError("CssColor must be a string")

        stripped = value.strip()
        if _HEX_PATTERN.match(stripped) or _NAME_PATTERN.match(stripped):
            return stripped
        if _FUNC_PATTERN.match(stripped):
            # Collapse internal whitespace is not needed; browsers accept it.
            return stripped

        raise ValueError(
            f"Invalid CSS color {value!r} " f"[{PreferencesRuleCodes.SUBTITLE_COLOR_INVALID}]"
        )


__all__ = ["CssColor"]
