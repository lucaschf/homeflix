"""External ID base class (re-export for backwards compatibility)."""

from src.building_blocks.domain.external_id import (
    BASE62_ALPHABET,
    RANDOM_PART_LENGTH,
    ExternalId,
)

__all__ = [
    "BASE62_ALPHABET",
    "ExternalId",
    "RANDOM_PART_LENGTH",
]
