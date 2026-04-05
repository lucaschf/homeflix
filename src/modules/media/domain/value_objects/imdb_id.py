"""IMDb ID value object for external metadata references."""

from pydantic import model_validator

from src.building_blocks.domain import StringValueObject


class ImdbId(StringValueObject):
    """IMDb identifier in tt1234567 format.

    Validates the standard IMDb ID pattern: 'tt' followed
    by 7 or more digits.

    Example:
        >>> imdb_id = ImdbId("tt1375666")
        >>> imdb_id.value
        'tt1375666'
    """

    @model_validator(mode="before")
    @classmethod
    def validate_format(cls, value: str) -> str:
        r"""Validate IMDb ID format.

        Args:
            value: The IMDb ID string.

        Returns:
            The validated value.

        Raises:
            ValueError: If format doesn't match tt\d{7,}.
        """
        if not isinstance(value, str):
            raise ValueError("IMDb ID must be a string")

        import re

        if not re.match(r"^tt\d{7,}$", value):
            raise ValueError("IMDb ID must match format tt1234567 (tt followed by 7+ digits)")

        return value


__all__ = ["ImdbId"]
