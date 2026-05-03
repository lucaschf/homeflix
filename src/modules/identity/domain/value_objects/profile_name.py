"""Profile name value object."""

from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject
from src.modules.identity.domain.rule_codes import IdentityRuleCodes


class ProfileName(StringValueObject):
    """Display name of a personalization profile.

    Constraints:
        - Trimmed; must not be empty after trimming.
        - Maximum 50 characters after trimming.

    Example:
        >>> ProfileName("Kids").value
        'Kids'
        >>> ProfileName("  Lucas  ").value
        'Lucas'
    """

    MAX_LENGTH: ClassVar[int] = 50

    @model_validator(mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        """Trim and validate the profile name."""
        if not isinstance(value, str):
            raise ValueError(
                f"Profile name must be a string [{IdentityRuleCodes.PROFILE_NAME_EMPTY}]"
            )

        trimmed = value.strip()

        if not trimmed:
            raise ValueError(
                f"Profile name cannot be empty [{IdentityRuleCodes.PROFILE_NAME_EMPTY}]"
            )

        if len(trimmed) > cls.MAX_LENGTH:
            raise ValueError(
                f"Profile name cannot exceed {cls.MAX_LENGTH} characters "
                f"[{IdentityRuleCodes.PROFILE_NAME_TOO_LONG}]"
            )

        return trimmed


__all__ = ["ProfileName"]
