"""Playback speed value object."""

from typing import Any, ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import FloatValueObject
from src.modules.preferences.domain.rule_codes import PreferencesRuleCodes


class Speed(FloatValueObject):
    """Video playback rate multiplier.

    Bounds match the frontend slider (``0.25x`` slow-motion to
    ``4.0x`` fast-forward). Mirrors the Pydantic validation already
    on ``UpdatePreferencesRequest`` in the presentation layer so the
    rule is authoritative in one place.

    Example:
        >>> Speed(1.0).value
        1.0
        >>> Speed(2.0).value
        2.0
    """

    MIN: ClassVar[float] = 0.25
    MAX: ClassVar[float] = 4.0

    @model_validator(mode="before")
    @classmethod
    def validate_range(cls, value: Any) -> float:
        """Ensure the speed falls within the allowed range."""
        try:
            as_float = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Speed must be a number, got {value!r}") from exc

        if not cls.MIN <= as_float <= cls.MAX:
            raise ValueError(
                f"Speed must be between {cls.MIN} and {cls.MAX}; got {as_float} "
                f"[{PreferencesRuleCodes.SPEED_OUT_OF_RANGE}]"
            )
        return as_float


__all__ = ["Speed"]
