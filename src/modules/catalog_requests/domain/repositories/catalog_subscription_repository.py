"""Repository interface for ``CatalogSubscription`` aggregates."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.catalog_requests.domain.entities import CatalogSubscription
from src.modules.catalog_requests.domain.value_objects import CatalogRequestId


class CatalogSubscriptionRepository(ABC):
    """Abstract repository for ``CatalogSubscription`` persistence.

    A subscription is keyed naturally by ``(request_id, user_id)`` —
    "this user wants this title's arrival ping". The
    ``CatalogSubscriptionId`` exists for soft-delete bookkeeping and
    cross-references, but every interesting query is by request, by
    user, or by the pair (ADR-022).
    """

    @abstractmethod
    async def add(self, subscription: CatalogSubscription) -> CatalogSubscription:
        """Persist a new subscription.

        Args:
            subscription: The aggregate to persist. Must have an ``id``.

        Returns:
            The persisted aggregate, refreshed from the database.
        """

    @abstractmethod
    async def find(
        self,
        request_id: CatalogRequestId,
        user_id: str,
    ) -> CatalogSubscription | None:
        """Look up a single subscription by its natural key.

        Backs the idempotent subscribe path: a repeat "Avisar quando
        chegar" on a title the user already follows must not create a
        duplicate row.

        Args:
            request_id: External id of the parent ``CatalogRequest``.
            user_id: External id (``usr_xxx``) of the subscriber.

        Returns:
            The matching ``CatalogSubscription`` or ``None``.
        """

    @abstractmethod
    async def list_for_request(
        self,
        request_id: CatalogRequestId,
    ) -> list[CatalogSubscription]:
        """List every active subscription for a request.

        The fanout read: when a title lands (auto via
        ``MediaEnrichedEvent`` or the admin "mark as included"
        action), each returned subscriber gets the "it arrived"
        notification.

        Args:
            request_id: External id of the parent ``CatalogRequest``.

        Returns:
            Active subscriptions for the request (empty when none).
        """

    @abstractmethod
    async def remove(
        self,
        request_id: CatalogRequestId,
        user_id: str,
    ) -> bool:
        """Soft-delete a subscription by its natural key (unsubscribe).

        Idempotent: removing a subscription that isn't there is not an
        error. The parent ``CatalogRequest`` is left untouched — the
        title stays in the queue even with zero subscribers.

        Args:
            request_id: External id of the parent ``CatalogRequest``.
            user_id: External id (``usr_xxx``) of the subscriber.

        Returns:
            ``True`` when a row was soft-deleted, ``False`` when no
            active subscription matched.
        """

    @abstractmethod
    async def count_for_request(self, request_id: CatalogRequestId) -> int:
        """Count active subscribers for a single request.

        Args:
            request_id: External id of the parent ``CatalogRequest``.

        Returns:
            Number of active subscriptions (the "N people waiting"
            figure).
        """

    @abstractmethod
    async def count_by_requests(
        self,
        request_ids: Sequence[CatalogRequestId],
    ) -> dict[CatalogRequestId, int]:
        """Batch subscriber counts keyed by request.

        Lets the admin queue and the "Em breve" grid render their
        subscriber counts in one round-trip instead of N+1 per-row
        lookups. Empty input returns an empty dict; requests with zero
        subscribers are simply absent from the mapping.

        Args:
            request_ids: Requests to count subscribers for.

        Returns:
            Mapping of ``request_id`` to its active subscriber count.
        """

    @abstractmethod
    async def request_ids_for_user(self, user_id: str) -> set[CatalogRequestId]:
        """Return the set of requests a user currently subscribes to.

        Powers the "is the caller subscribed?" flag on the member
        listing and the "só os que eu acompanho" filter without a
        per-row check.

        Args:
            user_id: External id (``usr_xxx``) of the subscriber.

        Returns:
            Set of ``request_id`` the user has an active subscription
            for (empty when none).
        """


__all__ = ["CatalogSubscriptionRepository"]
