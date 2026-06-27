"""Serialization helpers for the ``localized`` metadata column.

Bridges the :class:`LocalizedMetadata` value object (ADR-023) and the
JSON ``Text`` column. Kept in one place so every mapper stores/reads the
blob the same way (and the JSON encoding lives only here).
"""

import json

from src.modules.media.domain.value_objects.localized_metadata import LocalizedMetadata


def dump_localized(localized: LocalizedMetadata) -> str | None:
    """Serialize the value object to the stored JSON string, or ``None``.

    Returns ``None`` when there are no overrides so the column stays
    ``NULL`` instead of an empty ``{}`` blob (matching prior behavior).
    """
    data = localized.to_serializable()
    return json.dumps(data, ensure_ascii=False) if data else None


def load_localized(raw: str | None) -> LocalizedMetadata:
    """Build the value object from the stored JSON string (``None`` → empty)."""
    return LocalizedMetadata.from_serializable(json.loads(raw) if raw else None)


__all__ = ["dump_localized", "load_localized"]
