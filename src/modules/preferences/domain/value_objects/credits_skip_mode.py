"""CreditsSkipMode — what the player does when the end credits start."""

from enum import StrEnum


class CreditsSkipMode(StrEnum):
    """Per-profile behaviour at a title's credits onset.

    A :class:`CreditsMarker` records only the onset — credits run to the
    end of the file — so "skipping" them means moving on rather than
    seeking forward. Same division of labour as :class:`IntroSkipMode`:
    the server publishes marker plus preference, the player acts. On a
    title with nothing to advance to (a movie, a season finale) both
    modes collapse to the same thing. String values are the canonical
    ones persisted on the ``preferences`` table.

    Attributes:
        MANUAL: Surface the next-episode prompt from the onset and wait
            for the viewer to take it.
        AUTO: Start the next episode once the credits begin.
    """

    MANUAL = "manual"
    AUTO = "auto"


__all__ = ["CreditsSkipMode"]
