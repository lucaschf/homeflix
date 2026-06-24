"""Origin of a catalog request — who put the title in the queue."""

from __future__ import annotations

from enum import StrEnum


class CatalogRequestSource(StrEnum):
    """Where a ``CatalogRequest`` came from (ADR-022).

    Distinguishes a title a member explicitly asked for from one the
    household surfaced on its own (e.g. a needs-review flag that seeds
    a request). Fixed at creation — it records the *origin*, so a later
    subscriber expressing interest doesn't change it (their interest is
    a ``CatalogSubscription``, not the source).

    Uses ``StrEnum`` so the value serializes straight to the DTO and
    the database column.

    Example:
        >>> CatalogRequestSource.for_requester("usr_alice")
        <CatalogRequestSource.USER: 'user'>
        >>> CatalogRequestSource.for_requester(None)
        <CatalogRequestSource.HOUSEHOLD: 'household'>
    """

    USER = "user"
    HOUSEHOLD = "household"

    @classmethod
    def for_requester(cls, requester_user_id: str | None) -> CatalogRequestSource:
        """Derive the source from whether a member initiated the request.

        A known requester means a member asked for the title
        (:attr:`USER`); its absence means the household/system seeded
        it (:attr:`HOUSEHOLD`).
        """
        return cls.USER if requester_user_id else cls.HOUSEHOLD


__all__ = ["CatalogRequestSource"]
