"""Content rating value object for media content."""

from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain import StringValueObject


class ContentRating(StringValueObject):
    """Content rating classification for movies and series.

    Represents age/content classification labels such as G, PG, PG-13,
    R, NC-17, TV-MA, etc. Validates non-empty and max 20 characters.

    Example:
        >>> rating = ContentRating("PG-13")
        >>> rating.value
        'PG-13'
    """

    MAX_LENGTH: ClassVar[int] = 20

    @model_validator(mode="before")
    @classmethod
    def validate_content_rating(cls, value: str) -> str:
        """Validate the content rating string."""
        if not isinstance(value, str):
            raise ValueError("Content rating must be a string")

        value = value.strip()

        if not value:
            raise ValueError("Content rating cannot be empty")

        if len(value) > cls.MAX_LENGTH:
            raise ValueError(f"Content rating cannot exceed {cls.MAX_LENGTH} characters")

        return value


__all__ = ["ContentRating"]
