"""Library name value object."""

from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject
from src.modules.library.domain.rule_codes import LibraryRuleCodes


class LibraryName(StringValueObject):
    """Name of a media library.

    Constraints:
    - Must not be empty or whitespace only
    - Maximum 100 characters after trimming

    Example:
        >>> name = LibraryName("My Movies")
        >>> name.value
        'My Movies'
        >>> LibraryName("  Anime Collection  ").value
        'Anime Collection'
    """

    MAX_LENGTH: ClassVar[int] = 100

    @model_validator(mode="before")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Validate and normalize the library name.

        Args:
            value: The raw library name.

        Returns:
            The trimmed library name.

        Raises:
            ValueError: If name is empty or too long.
        """
        if not isinstance(value, str):
            raise ValueError("Library name must be a string")

        value = value.strip()

        if not value:
            raise ValueError(
                f"Library name cannot be empty [{LibraryRuleCodes.LIBRARY_NAME_EMPTY}]"
            )

        if len(value) > cls.MAX_LENGTH:
            raise ValueError(
                f"Library name cannot exceed {cls.MAX_LENGTH} characters "
                f"[{LibraryRuleCodes.LIBRARY_NAME_TOO_LONG}]"
            )

        return value


__all__ = ["LibraryName"]
