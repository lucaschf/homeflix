"""Metadata domain value objects."""

from src.modules.metadata.domain.value_objects.artwork_key import (
    ARTWORK_KEY_PATTERN,
    SUPPORTED_ARTWORK_CONTENT_TYPES,
    ArtworkKey,
)
from src.modules.metadata.domain.value_objects.artwork_variant import (
    ALLOWED_ARTWORK_WIDTHS,
    ARTWORK_WIDTH_LADDER,
    ArtworkKind,
    ArtworkWidth,
)

__all__ = [
    "ALLOWED_ARTWORK_WIDTHS",
    "ARTWORK_KEY_PATTERN",
    "ARTWORK_WIDTH_LADDER",
    "SUPPORTED_ARTWORK_CONTENT_TYPES",
    "ArtworkKey",
    "ArtworkKind",
    "ArtworkWidth",
]
