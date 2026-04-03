"""Subtitle display mode enumeration."""

from enum import StrEnum


class SubtitleMode(StrEnum):
    """When to display subtitles by default during playback.

    Controls automatic subtitle selection based on audio language
    and user preferences.

    Attributes:
        ALWAYS: Always show preferred subtitle language.
        FOREIGN_AUDIO_ONLY: Show subtitles only when audio is not in preferred language.
        FORCED_ONLY: Only show forced subtitles (signs, translations).
        NONE: Subtitles off by default.

    Example:
        >>> mode = SubtitleMode.FOREIGN_AUDIO_ONLY
        >>> mode.value
        'foreign'
    """

    ALWAYS = "always"
    FOREIGN_AUDIO_ONLY = "foreign"
    FORCED_ONLY = "forced"
    NONE = "none"


__all__ = ["SubtitleMode"]
