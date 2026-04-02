"""Duration value object for media content."""

from pydantic import model_validator

from src.building_blocks.domain import IntValueObject


class Duration(IntValueObject):
    """Duration in seconds for media content.

    Represents the length of a movie or episode in seconds.
    Must be non-negative (>= 0).

    Example:
        >>> duration = Duration(7200)  # 2 hours
        >>> duration.hours
        2
        >>> duration.format_hms()
        '02:00:00'
    """

    @model_validator(mode="before")
    @classmethod
    def validate_non_negative(cls, value: int) -> int:
        """Validate that duration is non-negative.

        Args:
            value: The duration in seconds.

        Returns:
            The validated duration value.

        Raises:
            ValueError: If duration is negative.
        """
        if not isinstance(value, int):
            raise ValueError("Duration must be an integer")

        if value < 0:
            raise ValueError("Duration must be non-negative")

        return value

    @property
    def minutes(self) -> int:
        """Return duration in whole minutes.

        Returns:
            The number of complete minutes in this duration.
        """
        return self.value // 60

    @property
    def hours(self) -> int:
        """Return duration in whole hours.

        Returns:
            The number of complete hours in this duration.
        """
        return self.value // 3600

    def format_hms(self) -> str:
        """Format duration as HH:MM:SS.

        Returns:
            A string in the format "HH:MM:SS".

        Example:
            >>> Duration(3723).format_hms()
            '01:02:03'
        """
        hours, remainder = divmod(self.value, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


__all__ = ["Duration"]
