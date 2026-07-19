"""Value object for a mirrored-artwork storage key (ADR-029).

The key is the stable, storage-safe token embedded verbatim in the
served URL ``/api/v1/artwork/{key}`` and used as the object name in
:class:`ArtworkStoragePort`. It is content-addressed — the SHA-256 of
the image bytes plus a type-bearing extension — so re-mirroring the
same image de-duplicates naturally and a changed image yields a new
key (cache-busting).

This VO is the single source of truth for the key charset: the proxy
route validates untrusted input against :data:`ARTWORK_KEY_PATTERN`,
and the mirror job constructs keys via :meth:`ArtworkKey.for_content`,
so the write path is guarded too — not just the read route.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject

#: Charset a storage key may use. Kept here so the route and the job
#: share one definition instead of restating the rule.
ARTWORK_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

# Explicit MIME -> extension map for the image types providers serve.
# Preferred over ``mimetypes.guess_extension``, which is unreliable
# across platforms (e.g. ``image/webp`` is unregistered on some Windows
# installs and ``image/jpeg`` can yield ``.jpe``).
_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}

# Fallback extension when neither the content type nor the source URL
# yields one. Artwork is always an image, so a generic image extension
# keeps the served content type sensible.
_FALLBACK_EXTENSION = ".jpg"


class ArtworkKey(StringValueObject):
    """A validated, content-addressed artwork storage key.

    Example:
        >>> key = ArtworkKey.for_content(
        ...     b"...bytes...",
        ...     content_type="image/png",
        ...     source_url="https://image.tmdb.org/t/p/original/x.png",
        ... )
        >>> str(key).endswith(".png")
        True
    """

    @model_validator(mode="before")
    @classmethod
    def validate_key(cls, value: str) -> str:
        """Reject anything outside the safe charset or that is all dots."""
        if not isinstance(value, str):
            raise ValueError("ArtworkKey must be a string")
        value = value.strip()
        if not ARTWORK_KEY_PATTERN.match(value) or set(value) <= {"."}:
            raise ValueError(
                "ArtworkKey must match [A-Za-z0-9._-]+ and not be all dots"
            )
        return value

    @classmethod
    def for_content(
        cls,
        content: bytes,
        *,
        content_type: str | None,
        source_url: str,
    ) -> ArtworkKey:
        """Build a content-addressed key from image bytes.

        Args:
            content: The downloaded image bytes.
            content_type: The response MIME type, used to pick the
                extension (``image/png`` -> ``.png``). Falls back to the
                source URL's suffix, then to ``.jpg``.
            source_url: The remote URL the bytes came from, used for the
                extension when ``content_type`` is missing/unknown.

        Returns:
            An ``ArtworkKey`` of the form ``<sha256-hex><ext>``.
        """
        digest = hashlib.sha256(content).hexdigest()
        return cls(f"{digest}{_extension_for(content_type, source_url)}")


def _extension_for(content_type: str | None, source_url: str) -> str:
    """Pick a file extension from the content type, else the URL, else jpg."""
    if content_type:
        # Strip any ``; charset=...`` suffix before the lookup.
        mime = content_type.split(";", 1)[0].strip().lower()
        if mime in _CONTENT_TYPE_EXTENSIONS:
            return _CONTENT_TYPE_EXTENSIONS[mime]
    suffix = _clean_suffix(urlsplit(source_url).path)
    return suffix or _FALLBACK_EXTENSION


def _clean_suffix(path: str) -> str:
    """Return a charset-safe extension from a URL path, or empty string."""
    dot = path.rfind(".")
    if dot == -1:
        return ""
    suffix = path[dot:]
    return suffix if ARTWORK_KEY_PATTERN.match(suffix.lstrip(".")) else ""


__all__ = ["ARTWORK_KEY_PATTERN", "ArtworkKey"]
