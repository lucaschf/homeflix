"""Honest, derived status of a catalog request."""

from enum import StrEnum


class CatalogRequestStatus(StrEnum):
    """Where a ``CatalogRequest`` stands, derived from ``fulfilled_at``.

    Deliberately thin (ADR-022): the system only honestly knows
    "still waiting" vs "the title landed". The richer pipeline states
    the design mock imagined (processing / waiting_file / matching)
    describe machinery that doesn't exist, so they're left out. A
    future ``STALLED`` (pending but the title is already in the catalog
    under a different tmdb id) can slot in here when there's a real
    signal for it.

    Not stored — computed on read from ``fulfilled_at`` so it can never
    drift from the source of truth.

    Example:
        >>> CatalogRequestStatus.PENDING.value
        'pending'
    """

    PENDING = "pending"
    FULFILLED = "fulfilled"


__all__ = ["CatalogRequestStatus"]
