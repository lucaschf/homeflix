"""List name value object."""

from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject
from src.modules.collections.domain.rule_codes import CollectionRuleCodes


class ListName(StringValueObject):
    """Name of a custom list or collection.

    Constraints:
    - Must not be empty or whitespace only
    - Maximum 100 characters after trimming

    Example:
        >>> name = ListName("Action Movies")
        >>> name.value
        'Action Movies'
        >>> ListName("  Anime Collection  ").value
        'Anime Collection'
    """

    MAX_LENGTH: ClassVar[int] = 100

    @model_validator(mode="before")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Validate and normalize the list name.

        Args:
            value: The raw list name.

        Returns:
            The trimmed list name.

        Raises:
            ValueError: If name is empty or too long.
        """
        if not isinstance(value, str):
            raise ValueError("List name must be a string")

        value = value.strip()

        if not value:
            raise ValueError(f"List name cannot be empty [{CollectionRuleCodes.LIST_NAME_EMPTY}]")

        if len(value) > cls.MAX_LENGTH:
            raise ValueError(
                f"List name cannot exceed {cls.MAX_LENGTH} characters "
                f"[{CollectionRuleCodes.LIST_NAME_TOO_LONG}]"
            )

        return value


__all__ = ["ListName"]
