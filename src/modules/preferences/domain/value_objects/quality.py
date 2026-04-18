"""Default playback quality enumeration."""

from enum import StrEnum


class Quality(StrEnum):
    """Preferred variant quality when multiple resolutions are available.

    String values are the canonical ones persisted on the
    ``preferences`` table. ``BEST`` asks the player to pick the
    highest-resolution variant available; ``AUTO`` defers the choice
    to the adaptive bitrate logic; the fixed levels pin the decision.
    """

    AUTO = "auto"
    BEST = "best"
    P1080 = "1080p"
    P720 = "720p"
    P480 = "480p"
    P360 = "360p"


__all__ = ["Quality"]
