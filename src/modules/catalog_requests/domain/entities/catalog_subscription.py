"""CatalogSubscription aggregate root."""

from __future__ import annotations

from pydantic import Field

from src.building_blocks.domain import AggregateRoot
from src.modules.catalog_requests.domain.value_objects import (
    CatalogRequestId,
    CatalogSubscriptionId,
)


class CatalogSubscription(AggregateRoot[CatalogSubscriptionId]):
    """One user's opt-in to be notified when a queued title arrives.

    ADR-022 splits "the title is in the queue" (``CatalogRequest``)
    from "who wants to be notified" (this aggregate). A subscription
    is a small, standalone aggregate — one row per
    ``(request_id, user_id)`` — rather than a collection nested inside
    ``CatalogRequest``, so a popular title doesn't force loading every
    subscriber just to add or count one.

    Fanout reads all subscriptions of a request and pings each
    ``user_id`` when the title lands (auto via ``MediaEnrichedEvent``
    or the admin "mark as included" action). Unsubscribing soft-deletes
    the row; the parent ``CatalogRequest`` survives with zero
    subscriptions because the queue tracks titles, not interest.

    The subscribe timestamp is the inherited ``created_at`` (from
    ``DomainEntity``) — no dedicated field, matching how
    ``CatalogRequest`` leans on the base timestamps.

    Attributes:
        id: External ID (``sub_xxx`` format).
        request_id: The ``CatalogRequest`` (queued title) this
            subscription belongs to.
        user_id: External id (``usr_xxx``) of the subscriber to notify
            on arrival. Stored as a string to match the requester
            anchor on ``CatalogRequest`` (no per-user VO in this BC).

    Example:
        >>> sub = CatalogSubscription.create(
        ...     request_id=request.id,
        ...     user_id="usr_3yL8nQsT9mK5",
        ... )
    """

    id: CatalogSubscriptionId | None = Field(default=None)

    request_id: CatalogRequestId
    user_id: str

    @classmethod
    def create(
        cls,
        request_id: CatalogRequestId,
        user_id: str,
    ) -> CatalogSubscription:
        """Factory method with automatic ID generation.

        Args:
            request_id: External id of the parent ``CatalogRequest``.
            user_id: External id (``usr_xxx``) of the subscribing user.

        Returns:
            A new ``CatalogSubscription`` instance.
        """
        return cls(
            id=CatalogSubscriptionId.generate(),
            request_id=request_id,
            user_id=user_id,
        )


__all__ = ["CatalogSubscription"]
