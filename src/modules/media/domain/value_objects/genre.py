"""Genre value object for media content."""

from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject


class Genre(StringValueObject):
    """Genre category for media content.

    Represents a genre like "Action", "Comedy", "Drama", etc.
    Must be non-empty with a maximum of 50 characters.

    Example:
        >>> genre = Genre("Action")
        >>> genre.value
        'Action'
    """

    MAX_LENGTH: ClassVar[int] = 50

    @model_validator(mode="before")
    @classmethod
    def validate_genre(cls, value: str) -> str:
        """Validate the genre string.

        Args:
            value: The raw genre string.

        Returns:
            The validated and trimmed genre string.

        Raises:
            ValueError: If the genre is empty or exceeds max length.
        """
        if not isinstance(value, str):
            raise ValueError("Genre must be a string")

        value = value.strip()

        if not value:
            raise ValueError("Genre cannot be empty")

        if len(value) > cls.MAX_LENGTH:
            raise ValueError(f"Genre cannot exceed {cls.MAX_LENGTH} characters")

        return value


__all__ = ["Genre"]
