"""Detection state of the credits-detection background job for a title."""

from enum import StrEnum


class CreditsDetectionState(StrEnum):
    """Lifecycle state of credits detection for a single title.

    Unlike intro detection (a season-scoped cross-correlation), credits
    detection is **per-file**: each movie and each episode is analysed
    independently for the end-credits onset. The state therefore lives on
    the individual title, not the season.

    Manual markers are independent of this state — a user can override a
    title's marker without changing its detection state.

    Attributes:
        NOT_STARTED: Default state for newly added media — the job has not
            yet picked it up.
        IN_PROGRESS: The job is currently processing this title.
        COMPLETED: The job ran and persisted a marker (credits onset was
            located with sufficient confidence).
        NO_CREDITS_FOUND: The job ran but found no confident credits onset
            (e.g. credits over footage, or below the confidence floor).
            Distinct from FAILED — the analysis succeeded, the content
            simply has no detectable signal.
        FAILED: The job ran but errored (e.g. ffmpeg decode failure).
        DISABLED: Detection is disabled for this title (e.g. ffmpeg not
            installed on the host, or the title is opted out).
    """

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    NO_CREDITS_FOUND = "NO_CREDITS_FOUND"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


__all__ = ["CreditsDetectionState"]
