"""IntroSkipMode — what the player does when it reaches an intro marker."""

from enum import StrEnum


class IntroSkipMode(StrEnum):
    """Per-profile behaviour at an episode's opening sequence.

    The server never skips anything — it has no playhead. This is the
    preference the player reads at startup and combines with the
    episode's ``intro`` marker to decide whether to offer a button or
    jump on its own. String values are the canonical ones persisted on
    the ``preferences`` table — the values the frontend sends and
    receives verbatim.

    Attributes:
        MANUAL: Offer a "skip intro" button while the playhead sits
            inside the marked window; never move the playhead unasked.
        AUTO: Jump straight to the end of the window.
        AUTO_AFTER_FIRST: Let the opening play on the first episode of a
            season, then behave like ``AUTO`` for the rest of it — for
            viewers who want to hear the theme once per season.
    """

    MANUAL = "manual"
    AUTO = "auto"
    AUTO_AFTER_FIRST = "autoAfterFirst"


__all__ = ["IntroSkipMode"]
