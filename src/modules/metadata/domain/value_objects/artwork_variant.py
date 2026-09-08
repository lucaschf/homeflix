"""Responsive artwork variants — kinds, widths and the shared ladder (ADR-034).

A mirrored artwork object is served at its original size, or as a
downscaled *variant* derived from it. The widths a variant may have
form a fixed ladder per artwork kind; it is the same ladder the
frontend puts in ``srcset`` and the same sizes the metadata provider
serves, so a URL built by the UI is valid whether the image is
mirrored or still remote. The ladder is domain knowledge: the route
validates untrusted input against it (like ``ARTWORK_KEY_PATTERN``),
the mirror job pre-generates it, and ``ArtworkKey.variant`` only
accepts a width from it, so an off-ladder object can never be minted.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import model_validator

from src.building_blocks.domain.value_objects import IntValueObject

if TYPE_CHECKING:
    from collections.abc import Mapping


class ArtworkKind(StrEnum):
    """What an artwork image depicts, which decides its width ladder."""

    POSTER = "poster"
    BACKDROP = "backdrop"
    LOGO = "logo"
    STILL = "still"


#: Every width some kind may be asked for — the union of the ladder.
#: What ``GET /api/v1/artwork/{key}?w=`` accepts; anything else is a 400.
ALLOWED_ARTWORK_WIDTHS: frozenset[int] = frozenset({300, 342, 500, 780, 1280})


class ArtworkWidth(IntValueObject):
    """A variant width in CSS pixels, restricted to the ladder.

    Example:
        >>> ArtworkWidth(780).value
        780
        >>> ArtworkWidth(999)
        Traceback (most recent call last):
        ...
        DomainValidationException: ...
    """

    @model_validator(mode="before")
    @classmethod
    def validate_width(cls, value: Any) -> Any:
        """Reject anything that is not one of the ladder widths."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("ArtworkWidth must be an integer")
        if value not in ALLOWED_ARTWORK_WIDTHS:
            raise ValueError(
                f"ArtworkWidth must be one of {sorted(ALLOWED_ARTWORK_WIDTHS)}, got {value}"
            )
        return value


#: Widths pre-generated (and advertised in ``srcset``) per kind, ascending.
#: Backdrops go full-bleed, posters/logos fill a card or a logo box, and
#: stills are episode thumbnails; the original is always the last resort.
ARTWORK_WIDTH_LADDER: Mapping[ArtworkKind, tuple[ArtworkWidth, ...]] = {
    ArtworkKind.BACKDROP: (ArtworkWidth(780), ArtworkWidth(1280)),
    ArtworkKind.POSTER: (ArtworkWidth(342), ArtworkWidth(500)),
    ArtworkKind.LOGO: (ArtworkWidth(300), ArtworkWidth(500)),
    ArtworkKind.STILL: (ArtworkWidth(300),),
}


__all__ = [
    "ALLOWED_ARTWORK_WIDTHS",
    "ARTWORK_WIDTH_LADDER",
    "ArtworkKind",
    "ArtworkWidth",
]
