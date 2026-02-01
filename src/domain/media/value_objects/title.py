"""Title value object for media content."""

import re
from typing import ClassVar

from pydantic import model_validator

from src.domain.shared.models import StringValueObject


class Title(StringValueObject):
    """Title for media content (movies, series, episodes).

    Validates and normalizes titles:
    - Strips leading/trailing whitespace
    - Collapses multiple whitespace characters to single space
    - Must be non-empty
    - Maximum 500 characters

    Example:
        >>> title = Title("  The   Dark   Knight  ")
        >>> title.value
        'The Dark Knight'
    """

    MAX_LENGTH: ClassVar[int] = 500

    @model_validator(mode="before")
    @classmethod
    def validate_and_normalize(cls, value: str) -> str:
        """Validate and normalize the title string.

        Args:
            value: The raw title string.

        Returns:
            The normalized title string.

        Raises:
            ValueError: If the title is empty or exceeds max length.
        """
        if not isinstance(value, str):
            raise ValueError("Title must be a string")

        # Normalize whitespace: replace all whitespace sequences with single space
        normalized = re.sub(r"\s+", " ", value).strip()

        if not normalized:
            raise ValueError("Title cannot be empty")

        if len(normalized) > cls.MAX_LENGTH:
            raise ValueError(f"Title cannot exceed {cls.MAX_LENGTH} characters")

        return normalized


__all__ = ["Title"]
