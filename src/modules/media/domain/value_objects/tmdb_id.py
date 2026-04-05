"""TMDB ID value object for external metadata references."""

from pydantic import model_validator

from src.building_blocks.domain import IntValueObject


class TmdbId(IntValueObject):
    """The Movie Database numeric ID.

    Validates that the ID is a positive integer.

    Example:
        >>> tmdb_id = TmdbId(27205)
        >>> tmdb_id.value
        27205
    """

    @model_validator(mode="before")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        """Validate that TMDB ID is positive.

        Args:
            value: The TMDB ID value.

        Returns:
            The validated value.

        Raises:
            ValueError: If value is not a positive integer.
        """
        if not isinstance(value, int):
            raise ValueError("TMDB ID must be an integer")
        if value <= 0:
            raise ValueError("TMDB ID must be positive")
        return value


__all__ = ["TmdbId"]
