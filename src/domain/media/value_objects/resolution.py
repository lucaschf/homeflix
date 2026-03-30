"""Resolution value object for media content."""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable

from pydantic import Field, model_validator

from src.domain.shared.exceptions.domain import DomainValidationException
from src.domain.shared.models import CompoundValueObject


class _ResolutionSpec(NamedTuple):
    """Typed specification for a named resolution."""

    width: int
    height: int


_RESOLUTION_MAP: dict[str, _ResolutionSpec] = {
    "360p": _ResolutionSpec(640, 360),
    "480p": _ResolutionSpec(854, 480),
    "720p": _ResolutionSpec(1280, 720),
    "1080p": _ResolutionSpec(1920, 1080),
    "2K": _ResolutionSpec(2560, 1440),
    "4K": _ResolutionSpec(3840, 2160),
    "Unknown": _ResolutionSpec(0, 0),
}

# Resolution categories
_SD_RESOLUTIONS: frozenset[str] = frozenset({"360p", "480p"})
_HD_RESOLUTIONS: frozenset[str] = frozenset({"720p", "1080p", "2K", "4K"})


class Resolution(CompoundValueObject):
    """Video resolution for media content.

    Stores width, height, and a human-readable name. Can be constructed
    from a name string (e.g., ``Resolution("1080p")``) which is looked
    up in a predefined resolution map, or from explicit dimensions.

    Valid named resolutions:
    - 360p (640x360, Standard Definition - Low)
    - 480p (854x480, Standard Definition)
    - 720p (1280x720, HD Ready)
    - 1080p (1920x1080, Full HD)
    - 2K (2560x1440)
    - 4K (3840x2160, Ultra HD)
    - Unknown (0x0, fallback for undetermined resolution)

    Example:
        >>> resolution = Resolution("1080p")
        >>> resolution.width
        1920
        >>> resolution.height
        1080
        >>> resolution.is_hd
        True
        >>> Resolution("4K") > Resolution("1080p")
        True
    """

    VALID_NAMES: ClassVar[frozenset[str]] = frozenset(_RESOLUTION_MAP.keys())

    width: int = Field(ge=0)
    height: int = Field(ge=0)
    name: str

    def __init__(self, name_or_data: Any = None, /, **kwargs: Any) -> None:
        """Create a Resolution from a name string or explicit fields.

        Args:
            name_or_data: Resolution name (e.g., "1080p") or omitted for kwargs.
            **kwargs: Explicit width, height, name fields.
        """
        if isinstance(name_or_data, str):
            super().__init__(**self._resolve_name(name_or_data.strip()))
        elif name_or_data is not None:
            super().__init__(**name_or_data) if isinstance(
                name_or_data, dict
            ) else super().__init__(**kwargs)
        else:
            super().__init__(**kwargs)

    @model_validator(mode="before")
    @classmethod
    def _coerce_from_string(cls, data: Any) -> Any:
        """Handle string input in Pydantic field validation contexts."""
        if isinstance(data, str):
            return cls._resolve_name(data.strip())
        return data

    @classmethod
    def _resolve_name(cls, name: str) -> dict[str, int | str]:
        """Look up a resolution name in the predefined map.

        Args:
            name: Resolution name (e.g., "1080p").

        Returns:
            Dict with width, height, name.

        Raises:
            DomainValidationException: If name is not recognised.
        """
        try:
            spec = _RESOLUTION_MAP[name]
        except KeyError as e:
            valid = ", ".join(sorted(cls.VALID_NAMES))
            raise DomainValidationException.single_field(
                object_type="Resolution",
                field="name",
                code="INVALID_RESOLUTION",
                message=f"Resolution must be one of: {valid}",
            ) from e

        return {"name": name, "width": spec.width, "height": spec.height}

    @classmethod
    def from_name(cls, name: str) -> Resolution:
        """Explicit factory from a resolution name.

        Args:
            name: Resolution name (e.g., "1080p").

        Returns:
            A Resolution instance.
        """
        return cls(name)

    @classmethod
    def unknown(cls) -> Resolution:
        """Factory method for unknown resolution.

        Returns:
            A Resolution instance with value "Unknown".
        """
        return cls("Unknown")

    # ── backward-compat property ──────────────────────────────────────

    @property
    def value(self) -> str:
        """Return the resolution name (backward compat with StringValueObject).

        Returns:
            The human-readable resolution name.
        """
        return self.name

    # ── computed properties ───────────────────────────────────────────

    @property
    def total_pixels(self) -> int:
        """Return total pixel count (width * height)."""
        return self.width * self.height

    @property
    def is_sd(self) -> bool:
        """Check if resolution is Standard Definition.

        Returns:
            True if resolution is 360p or 480p.
        """
        return self.name in _SD_RESOLUTIONS

    @property
    def is_hd(self) -> bool:
        """Check if the resolution is HD or higher.

        Returns:
            True if resolution is 720p, 1080p, 2K, or 4K.
        """
        return self.name in _HD_RESOLUTIONS

    @property
    def is_4k(self) -> bool:
        """Check if resolution is 4K.

        Returns:
            True if resolution is 4K.
        """
        return self.name == "4K"

    # ── comparison operators (by total_pixels) ────────────────────────

    def _compare(self, other: object, op: Callable[[int, int], bool]) -> bool:
        if not isinstance(other, Resolution):
            return NotImplemented
        return op(self.total_pixels, other.total_pixels)

    def __gt__(self, other: object) -> bool:
        return self._compare(other, operator.gt)

    def __lt__(self, other: object) -> bool:
        return self._compare(other, operator.lt)

    def __ge__(self, other: object) -> bool:
        return self._compare(other, operator.ge)

    def __le__(self, other: object) -> bool:
        return self._compare(other, operator.le)

    # ── string representation ─────────────────────────────────────────

    def __str__(self) -> str:
        """Return the resolution name."""
        return self.name

    def __repr__(self) -> str:
        """Return a detailed string representation."""
        return f"Resolution('{self.name}')"


__all__ = ["Resolution"]
