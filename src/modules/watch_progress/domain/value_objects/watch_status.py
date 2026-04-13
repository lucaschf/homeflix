"""Watch progress status enum."""

from enum import StrEnum


class WatchStatus(StrEnum):
    """Status of a watch progress record.

    Attributes:
        IN_PROGRESS: Media is partially watched.
        COMPLETED: Media has been watched past the completion threshold.

    Example:
        >>> WatchStatus.IN_PROGRESS
        'in_progress'
        >>> WatchStatus("completed") == "completed"
        True
    """

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


__all__ = ["WatchStatus"]
