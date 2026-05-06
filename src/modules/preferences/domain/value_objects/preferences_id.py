"""Preferences external ID value object.

Unlike the catalog IDs that follow the 12-char base62 scheme
(see ADR-002), a preferences row is singleton-per-profile and its
external ID mirrors the owning ``ProfileId``. The VO guards the
``prf_<slug>`` shape so arbitrary strings can't be persisted as ids
while keeping legacy ``prf_default`` rows readable until they are
migrated away.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject
from src.modules.preferences.domain.rule_codes import PreferencesRuleCodes

if TYPE_CHECKING:
    from src.shared_kernel.value_objects.profile_id import ProfileId


class PreferencesId(StringValueObject):
    """External id of a playback preferences record.

    Format: ``prf_<slug>`` where ``slug`` is 1-64 chars of
    ``[a-zA-Z0-9_-]``. New rows mirror the owning ``ProfileId``
    so the surrogate key never drifts from the natural key.

    Example:
        >>> PreferencesId("prf_default").value
        'prf_default'
    """

    PREFIX: ClassVar[str] = "prf"
    _PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^prf_[A-Za-z0-9_-]{1,64}$")

    @model_validator(mode="before")
    @classmethod
    def validate_format(cls, value: Any) -> str:
        """Validate the ``prf_<slug>`` shape."""
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
    def for_profile(cls, profile_id: ProfileId) -> PreferencesId:
        """Build the canonical id mirroring ``profile_id``.

        Reusing the profile_id string as the preferences external_id
        keeps the singleton-per-profile invariant explicit at the
        identity level — no separate id allocation is needed and the
        DB unique on ``profile_id`` doubles as a uniqueness guarantee
        on ``external_id``.
        """
        return cls(profile_id.value)


__all__ = ["PreferencesId"]
