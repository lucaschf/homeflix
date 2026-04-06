"""ImageUrl value object for poster/backdrop references."""

import re

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject

_HTTP_PATTERN = re.compile(r"^https?://\S+$")
_WINDOWS_PATH_PATTERN = re.compile(r"^[a-zA-Z]:[\\/]")


class ImageUrl(StringValueObject):
    r"""URL or absolute path to an image resource.

    Accepts:
    - HTTP/HTTPS URLs (e.g., https://image.tmdb.org/t/p/original/abc.jpg)
    - Absolute filesystem paths (e.g., /thumbnails/poster.jpg, C:\images\poster.jpg)

    Example:
        >>> url = ImageUrl("https://image.tmdb.org/t/p/original/abc.jpg")
        >>> url.value
        'https://image.tmdb.org/t/p/original/abc.jpg'
        >>> url.is_remote
        True
    """

    @model_validator(mode="before")
    @classmethod
    def validate_image_url(cls, value: str) -> str:
        """Validate that value is an HTTP URL or absolute path."""
        if not isinstance(value, str):
            raise ValueError("ImageUrl must be a string")

        value = value.strip()
        if not value:
            raise ValueError("ImageUrl cannot be empty")

        if _HTTP_PATTERN.match(value):
            return value

        # Check absolute path (Unix or Windows)
        if value.startswith("/") or _WINDOWS_PATH_PATTERN.match(value):
            return value

        raise ValueError("ImageUrl must be an HTTP/HTTPS URL or an absolute filesystem path")

    @property
    def is_remote(self) -> bool:
        """Check if this is a remote URL (not a local path)."""
        return self.value.startswith("http")


__all__ = ["ImageUrl"]
