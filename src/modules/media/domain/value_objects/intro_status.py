"""IntroStatus — where an episode stands on having its intro resolved."""

from enum import StrEnum


class IntroStatus(StrEnum):
    """Whether an episode's opening sequence has been settled.

    An episode without a marker is ambiguous on its own: nobody may have
    looked at it yet, or someone may have looked and found there is no
    opening sequence to skip. Collapsing both into "no marker" leaves a
    series permanently short of full coverage. This enum names the three
    states so callers stop inferring them from a nullable field.

    Attributes:
        PENDING: No marker and no decision — still needs review.
        MARKED: An intro span is recorded (auto-detected or manual).
        ABSENT: Someone confirmed this episode has no intro. Counts as
            resolved for coverage, and auto-detection skips it.
    """

    PENDING = "PENDING"
    MARKED = "MARKED"
    ABSENT = "ABSENT"


__all__ = ["IntroStatus"]
