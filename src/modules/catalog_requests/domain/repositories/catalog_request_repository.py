"""Repository interface for ``CatalogRequest`` aggregates."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.modules.catalog_requests.domain.value_objects import RequestedMediaType


class CatalogRequestRepository(ABC):
    """Abstract repository for ``CatalogRequest`` persistence.

    The aggregate is keyed externally by ``(tmdb_id, media_type)``
    rather than the internal ``CatalogRequestId``: every API entry
    point speaks TMDB ids, and treating ``(tmdb_id, media_type)`` as
    the natural key keeps the API surface idempotent without an
    extra round-trip through ``id``.
    """

    @abstractmethod
    async def find_by_tmdb_id(
        self,
        tmdb_id: int,
        media_type: RequestedMediaType,
    ) -> CatalogRequest | None:
        """Look up a single request by its TMDB target.

        Args:
            tmdb_id: TMDB numeric id.
            media_type: Whether the target is a movie or series.

        Returns:
            The matching ``CatalogRequest`` or ``None`` when no
            request has been registered for this title.
        """

    @abstractmethod
    async def find_by_tmdb_ids(
        self,
        tmdb_ids: Sequence[int],
        media_type: RequestedMediaType,
    ) -> dict[int, CatalogRequest]:
        """Batch lookup keyed by TMDB id.

        Used by the cross-BC read port to enrich a Collection Detail
        response in a single round-trip rather than N+1 lookups.
        Empty input returns an empty dict.

        Args:
            tmdb_ids: TMDB ids to resolve.
            media_type: Whether the targets are movies or series.

        Returns:
            Mapping of ``tmdb_id`` to ``CatalogRequest`` for the ids
            that have a registered request. Ids without a request are
            simply absent from the dict.
        """

    @abstractmethod
    async def list_pending(
        self,
        collection_tmdb_id: int | None = None,
    ) -> list[CatalogRequest]:
        """List unfulfilled requests, optionally scoped to a franchise.

        Args:
            collection_tmdb_id: When supplied, only return requests
                originally registered against this TMDB collection.
                Useful for the Collection Detail "X pending in this
                saga" indicator.

        Returns:
            Pending ``CatalogRequest`` aggregates ordered by most
            recently registered.
        """

    @abstractmethod
    async def add(self, request: CatalogRequest) -> CatalogRequest:
        """Persist a new request.

        Args:
            request: The aggregate to persist. Must have an ``id``.

        Returns:
            The persisted aggregate, refreshed from the database.
        """

    @abstractmethod
    async def update(self, request: CatalogRequest) -> CatalogRequest:
        """Update an existing request.

        Args:
            request: The updated aggregate.

        Returns:
            The persisted aggregate, refreshed from the database.
        """


__all__ = ["CatalogRequestRepository"]
