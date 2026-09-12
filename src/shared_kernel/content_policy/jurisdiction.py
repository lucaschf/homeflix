"""Vocabulary for choosing between disagreeing certification boards (ADR-035).

Lives in the shared kernel because two contexts need the same word for
the same idea: ``settings`` persists the household's choice, and
``media`` acts on it when normalizing a title. Neither may import the
other (ADR-009), and the meaning is policy rather than configuration
plumbing, so the enum belongs to the shared vocabulary rather than to
either side.
"""

from enum import StrEnum


class ContentRatingFallback(StrEnum):
    """What to do when no preferred jurisdiction rated a title.

    Attributes:
        STRICTEST_AVAILABLE: Take the most restrictive rating from any
            board that issued one. Keeps coverage high — a title rated
            only in France still gets an age — at the cost of sometimes
            applying a stricter board's reading than the household
            picked.
        NONE: Leave the title undetermined, which the domain resolves to
            adult. Highest precision, lowest coverage.
    """

    STRICTEST_AVAILABLE = "strictest_available"
    NONE = "none"


__all__ = ["ContentRatingFallback"]
