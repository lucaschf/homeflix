"""Detection state of the intro-detection background job for a Season."""

from enum import StrEnum


class IntroDetectionState(StrEnum):
    """Lifecycle state of intro detection for a Season.

    The auto-detection job is a season-scoped operation: it correlates
    audio fingerprints across episodes to find the common intro segment.
    The state tracks whether the job has run, succeeded, or skipped a
    season (e.g. because there are too few episodes to correlate).

    Manual markers on individual episodes are independent of this state —
    a user can override a single episode's marker without changing the
    Season's detection state.

    Attributes:
        NOT_STARTED: Default state for a newly added season — the job
            has not yet picked it up.
        IN_PROGRESS: The job is currently processing this season.
        COMPLETED: The job ran and persisted markers for the episodes
            where the intro could be located with sufficient confidence.
        FAILED: The job ran but failed (e.g. ffmpeg/fpcalc error,
            algorithm could not converge). ``intro_detection_error``
            holds the diagnostic message.
        INSUFFICIENT_EPISODES: The season has fewer episodes than
            required by the cross-correlation algorithm — typically
            seasons with 1-2 episodes. Will be retried if more
            episodes are added.
        DISABLED: Detection is disabled for this season (e.g. fpcalc
            not installed on the host, or the season is opted out).
    """

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INSUFFICIENT_EPISODES = "INSUFFICIENT_EPISODES"
    DISABLED = "DISABLED"


__all__ = ["IntroDetectionState"]
