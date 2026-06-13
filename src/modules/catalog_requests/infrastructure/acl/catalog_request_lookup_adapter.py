"""Adapter implementing ``CatalogRequestLookupPort`` for the Media BC.

This is the only file in the Catalog Requests BC that imports
from a port defined in another bounded context. The adapter
opens a short-lived Catalog Requests Unit of Work, batch-loads
the requested rows, and returns plain ``CatalogRequestStatus``
DTOs the Media BC can consume without leaking aggregate types.
"""

from collections.abc import Sequence

from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.media.application.ports.catalog_request_lookup_port import (
    CatalogRequestLookupPort,
    CatalogRequestStatus,
)
from src.shared_kernel.value_objects import MediaType


class CatalogRequestLookupAdapter(CatalogRequestLookupPort):
    """Resolve catalog-request status via the Catalog Requests UoW."""

    def __init__(self, uow_factory: CatalogRequestsUnitOfWorkFactory) -> None:
        """Initialize the adapter.

        Args:
            uow_factory: Factory for the Catalog Requests UoW.
        """
        self._uow_factory = uow_factory

    async def get_for_movie_tmdb_ids(
        self,
        tmdb_ids: Sequence[int],
    ) -> dict[int, CatalogRequestStatus]:
        """Batch-load request status for a set of movie TMDB ids."""
        if not tmdb_ids:
            return {}

        async with self._uow_factory() as uow:
            requests_by_id = await uow.catalog_requests.find_by_tmdb_ids(
                tmdb_ids,
                MediaType.MOVIE,
            )

        return {
            tmdb_id: CatalogRequestStatus(
                is_requested=True,
                notify_on_arrival=req.notify_on_arrival,
                is_fulfilled=req.is_fulfilled,
            )
            for tmdb_id, req in requests_by_id.items()
        }


__all__ = ["CatalogRequestLookupAdapter"]
