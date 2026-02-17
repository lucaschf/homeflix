"""Resolution value object for media content."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field, model_validator

from src.domain.shared.exceptions.domain import DomainValidationException
from src.domain.shared.models import CompoundValueObject

# Lookup map: resolution name → (width, height)
_RESOLUTION_MAP: dict[str, dict[str, Any]] = {
    "360p": {"width": 640, "height": 360, "name": "360p"},
    "480p": {"width": 854, "height": 480, "name": "480p"},
    "720p": {"width": 1280, "height": 720, "name": "720p"},
    "1080p": {"width": 1920, "height": 1080, "name": "1080p"},
    "2K": {"width": 2560, "height": 1440, "name": "2K"},
    "4K": {"width": 3840, "height": 2160, "name": "4K"},
    "Unknown": {"width": 0, "height": 0, "name": "Unknown"},
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
            name_or_data: Resolution name (e.g., "1080p") or dict of fields.
            **kwargs: Explicit width, height, name fields.

        Raises:
            DomainValidationException: If input is invalid.
        """
        try:
            if isinstance(name_or_data, str):
                data = self._resolve_name(name_or_data.strip())
                super().__init__(**data)
            elif isinstance(name_or_data, dict):
                super().__init__(**name_or_data)
            elif name_or_data is not None:
                raise ValueError(
                    f"Resolution expects a string name or keyword args, "
                    f"got {type(name_or_data)}"
                )
            else:
                super().__init__(**kwargs)
        except ValueError as e:
            if isinstance(e, DomainValidationException):
                raise
            raise DomainValidationException.single_field(
                object_type="Resolution",
                field="name",
                code="INVALID_RESOLUTION",
                message=str(e),
            ) from e

    @model_validator(mode="before")
    @classmethod
    def _coerce_from_string(cls, data: Any) -> Any:
        """Handle string input in Pydantic field validation contexts."""
        if isinstance(data, str):
            return cls._resolve_name(data.strip())
        return data

    @staticmethod
    def _resolve_name(name: str) -> dict[str, Any]:
        """Look up a resolution name in the predefined map.

        Args:
            name: Resolution name (e.g., "1080p").

        Returns:
            Dict with width, height, name.

        Raises:
            ValueError: If name is not recognised.
        """
        if name in _RESOLUTION_MAP:
            return _RESOLUTION_MAP[name]
        valid = ", ".join(sorted(_RESOLUTION_MAP.keys()))
        raise ValueError(f"Resolution must be one of: {valid}")

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

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Resolution):
            return NotImplemented
        return self.total_pixels > other.total_pixels

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Resolution):
            return NotImplemented
        return self.total_pixels < other.total_pixels

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Resolution):
            return NotImplemented
        return self.total_pixels >= other.total_pixels

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Resolution):
            return NotImplemented
        return self.total_pixels <= other.total_pixels

    # ── string representation ─────────────────────────────────────────

    def __str__(self) -> str:
        """Return the resolution name."""
        return self.name

    def __repr__(self) -> str:
        """Return a detailed string representation."""
        return f"Resolution('{self.name}')"


__all__ = ["Resolution"]
