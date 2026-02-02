"""Resolution value object for media content."""

from typing import ClassVar

from pydantic import model_validator

from src.domain.shared.models import StringValueObject


class Resolution(StringValueObject):
    """Video resolution for media content.

    Valid resolutions:
    - 360p (Standard Definition - Low)
    - 480p (Standard Definition)
    - 720p (HD Ready)
    - 1080p (Full HD)
    - 2K (2560x1440)
    - 4K (Ultra HD, 3840x2160)
    - Unknown (fallback for undetermined resolution)

    Example:
        >>> resolution = Resolution("1080p")
        >>> resolution.is_hd
        True
        >>> resolution = Resolution("480p")
        >>> resolution.is_sd
        True
    """

    # Resolution categories
    SD_RESOLUTIONS: ClassVar[frozenset[str]] = frozenset({"360p", "480p"})
    HD_RESOLUTIONS: ClassVar[frozenset[str]] = frozenset({"720p", "1080p", "2K", "4K"})
    UNKNOWN_RESOLUTION: ClassVar[str] = "Unknown"

    VALID_RESOLUTIONS: ClassVar[frozenset[str]] = frozenset(
        SD_RESOLUTIONS | HD_RESOLUTIONS | {UNKNOWN_RESOLUTION}
    )

    @model_validator(mode="before")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        """Validate the resolution string.

        Args:
            value: The raw resolution string.

        Returns:
            The validated resolution string.

        Raises:
            ValueError: If resolution is not in the valid set.
        """
        if not isinstance(value, str):
            raise ValueError("Resolution must be a string")

        value = value.strip()

        if value not in cls.VALID_RESOLUTIONS:
            valid = ", ".join(sorted(cls.VALID_RESOLUTIONS))
            raise ValueError(f"Resolution must be one of: {valid}")

        return value

    @classmethod
    def unknown(cls) -> "Resolution":
        """Factory method for unknown resolution.

        Returns:
            A Resolution instance with value "Unknown".
        """
        return cls("Unknown")

    @property
    def is_sd(self) -> bool:
        """Check if resolution is Standard Definition.

        Returns:
            True if resolution is 360p or 480p.
        """
        return self.value in self.SD_RESOLUTIONS

    @property
    def is_hd(self) -> bool:
        """Check if the resolution is HD or higher.

        Returns:
            True if resolution is 720p, 1080p, 2K, or 4K.
        """
        return self.value in self.HD_RESOLUTIONS

    @property
    def is_4k(self) -> bool:
        """Check if resolution is 4K.

        Returns:
            True if resolution is 4K.
        """
        return self.value == "4K"


__all__ = ["Resolution"]
