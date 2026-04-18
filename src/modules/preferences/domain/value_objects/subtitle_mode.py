"""Subtitle mode enumeration for playback preferences."""

from enum import StrEnum


class SubtitleMode(StrEnum):
    """Default subtitle behavior during playback.

    String values are the canonical ones persisted on the
    ``preferences`` table — the values the frontend sends and
    receives verbatim.

    Attributes:
        OFF: Never show subtitles.
        FOREIGN_ONLY: Show subtitles only when the audio track does
            not match the user's preferred language.
        ALWAYS: Always show preferred-language subtitles.
        FORCED_ONLY: Show only forced subtitles (on-screen signs /
            foreign-language lines baked into the source).
    """

    OFF = "off"
    FOREIGN_ONLY = "foreignOnly"
    ALWAYS = "always"
    FORCED_ONLY = "forcedOnly"


__all__ = ["SubtitleMode"]
