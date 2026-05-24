"""Title value object for media content."""

import re
import unicodedata
from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain import StringValueObject


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

    @property
    def normalized(self) -> str:
        """Canonical comparison key for content-identity matching.

        Lower-cases (case-fold), strips diacritics (NFKD decomposition
        dropping combining marks), and collapses whitespace, so titles
        that differ only in casing or accents compare equal. Used by
        the scanner's ``(normalized_original_title, year)`` dedup
        fallback (ADR-015); deterministic so repeated scans agree.

        Example:
            >>> Title("A Viagem de Chihiro").normalized
            'a viagem de chihiro'
            >>> Title("Amélie").normalized == Title("AMELIE").normalized
            True
        """
        decomposed = unicodedata.normalize("NFKD", self.value)
        without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", without_marks).strip().casefold()


__all__ = ["Title"]
