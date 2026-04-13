"""Season number value object for media content."""

from pydantic import model_validator

from src.building_blocks.domain import IntValueObject


class SeasonNumber(IntValueObject):
    """Season number within a series.

    Must be non-negative (>= 0). Season 0 represents specials.

    Example:
        >>> season = SeasonNumber(1)
        >>> season.value
        1
        >>> specials = SeasonNumber(0)
        >>> specials.value
        0
    """

    @model_validator(mode="before")
    @classmethod
    def validate_non_negative(cls, value: int) -> int:
        """Validate that season number is non-negative."""
        if not isinstance(value, int):
            raise ValueError("Season number must be an integer")

        if value < 0:
            raise ValueError("Season number must be non-negative")

        return value


__all__ = ["SeasonNumber"]
