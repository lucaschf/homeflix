"""Year value object for media content."""

from datetime import datetime
from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain import IntValueObject


class Year(IntValueObject):
    """Release year for media content.

    Validates that the year is within a reasonable range:
    - Minimum: 1800 (covers early cinema history)
    - Maximum: current year + 10 (allows for announced future releases)

    Example:
        >>> year = Year(2024)
        >>> year.value
        2024
    """

    MIN_YEAR: ClassVar[int] = 1800
    MAX_YEAR_OFFSET: ClassVar[int] = 10

    @model_validator(mode="before")
    @classmethod
    def validate_year_range(cls, value: int) -> int:
        """Validate that year is within the allowed range.

        Args:
            value: The year value.

        Returns:
            The validated year value.

        Raises:
            ValueError: If year is outside the valid range.
        """
        if not isinstance(value, int):
            raise ValueError("Year must be an integer")

        current_year = datetime.now().year
        max_year = current_year + cls.MAX_YEAR_OFFSET

        if value < cls.MIN_YEAR:
            raise ValueError(f"Year must be at least {cls.MIN_YEAR}")

        if value > max_year:
            raise ValueError(f"Year cannot exceed {max_year}")

        return value


__all__ = ["Year"]
