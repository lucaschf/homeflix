"""Air date value object for media content."""

from datetime import date, timedelta
from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain import DateValueObject


class AirDate(DateValueObject):
    """Original air date for episodes and seasons.

    Validates that the date is within a reasonable range:
    - Minimum: 1800-01-01 (covers early cinema history)
    - Maximum: today + 2 years (allows for announced future releases)

    Example:
        >>> air_date = AirDate(date(2024, 1, 15))
        >>> air_date.value
        datetime.date(2024, 1, 15)
        >>> str(air_date)
        '2024-01-15'
    """

    MIN_DATE: ClassVar[date] = date(1800, 1, 1)
    MAX_YEARS_AHEAD: ClassVar[int] = 2

    @model_validator(mode="before")
    @classmethod
    def validate_date_range(cls, value: date) -> date:
        """Validate that air date is within the allowed range.

        Args:
            value: The date value.

        Returns:
            The validated date value.

        Raises:
            ValueError: If date is outside the valid range.
        """
        if not isinstance(value, date):
            raise ValueError("AirDate must be a date")

        if value < cls.MIN_DATE:
            raise ValueError(f"Air date cannot be before {cls.MIN_DATE.isoformat()}")

        max_date = date.today() + timedelta(days=cls.MAX_YEARS_AHEAD * 365)
        if value > max_date:
            raise ValueError(f"Air date cannot be after {max_date.isoformat()}")

        return value


__all__ = ["AirDate"]
