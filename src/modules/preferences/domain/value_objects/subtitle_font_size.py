"""Subtitle font-size enumeration."""

from enum import StrEnum


class SubtitleFontSize(StrEnum):
    """Relative subtitle text size the player maps to a concrete size.

    Kept as three relative steps rather than a pixel value so the player
    can scale them to the viewport (the same tier renders larger on a TV
    than on a phone). String values are the canonical ones persisted on
    the ``preferences`` table.
    """

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


__all__ = ["SubtitleFontSize"]
