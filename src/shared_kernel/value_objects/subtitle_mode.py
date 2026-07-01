"""Subtitle display mode — shared playback-selection vocabulary."""

from enum import StrEnum


class SubtitleMode(StrEnum):
    """Default subtitle behavior during playback.

    Shared cross-module vocabulary (ADR-026): the Preferences BC persists
    the per-user choice, and the Media BC's ``TrackSelector.select_subtitle``
    consumes it to resolve the default subtitle. String values are the
    canonical ones persisted on the ``preferences`` table — the values the
    frontend sends and receives verbatim.

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
