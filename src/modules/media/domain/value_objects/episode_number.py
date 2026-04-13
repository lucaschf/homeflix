"""Episode number value object for media content."""

from pydantic import model_validator

from src.building_blocks.domain import IntValueObject


class EpisodeNumber(IntValueObject):
    """Episode number within a season.

    Must be positive (>= 1).

    Example:
        >>> episode = EpisodeNumber(1)
        >>> episode.value
        1
    """

    @model_validator(mode="before")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        """Validate that episode number is positive."""
        if not isinstance(value, int):
            raise ValueError("Episode number must be an integer")

        if value < 1:
            raise ValueError("Episode number must be at least 1")

        return value


__all__ = ["EpisodeNumber"]
