"""Preferences external ID value object.

Unlike the catalog IDs that follow the 12-char base62 scheme
(see ADR-002), a preferences row is singleton-per-user and its
external ID encodes the user_key itself (``prf_<user_key>``).
Until an auth system lands the only key is ``default``; the VO
just guards the ``prf_<slug>`` shape so arbitrary strings can't
be persisted as ids.
"""

import re
from typing import Any, ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject
from src.modules.preferences.domain.rule_codes import PreferencesRuleCodes


class PreferencesId(StringValueObject):
    """External id of a playback preferences record.

    Format: ``prf_<user_key>`` where ``user_key`` is 1-64 chars of
    ``[a-zA-Z0-9_-]``.

    Example:
        >>> PreferencesId("prf_default").value
        'prf_default'
    """

    PREFIX: ClassVar[str] = "prf"
    _PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^prf_[A-Za-z0-9_-]{1,64}$")

    @model_validator(mode="before")
    @classmethod
    def validate_format(cls, value: Any) -> str:
        """Validate the ``prf_<user_key>`` shape."""
        if not isinstance(value, str):
            raise ValueError("PreferencesId must be a string")

        value = value.strip()

        if not cls._PATTERN.match(value):
            raise ValueError(
                f"Invalid PreferencesId format: '{value}' "
                f"[{PreferencesRuleCodes.PREFERENCES_ID_INVALID}]"
            )

        return value

    @classmethod
    def for_user_key(cls, user_key: str) -> "PreferencesId":
        """Build the canonical id for a given user key."""
        return cls(f"{cls.PREFIX}_{user_key}")


__all__ = ["PreferencesId"]
