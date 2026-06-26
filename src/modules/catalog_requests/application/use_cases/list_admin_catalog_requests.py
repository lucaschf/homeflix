"""List pending catalog requests enriched for the admin queue."""

from src.modules.catalog_requests.application.dtos import (
    AdminCatalogRequestItem,
    CatalogRequestOutput,
)
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWorkFactory,
)


class ListAdminCatalogRequestsUseCase:
    """Pending requests + subscriber counts for the admin queue (ADR-022).

    The admin counterpart to the member feed: every pending request
    with its ``subscriber_count`` ("Inscritos"). ``source`` and the
    derived ``status`` already ride on the base DTO. Counts are
    resolved in one batch query rather than N+1.
    """

    def __init__(self, uow_factory: CatalogRequestsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh catalog-requests
                Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, lang: str = "en") -> list[AdminCatalogRequestItem]:
        """Return every pending request annotated with its subscriber count.

        Args:
            lang: Language for the per-request localized title snapshot.
        """
        async with self._uow_factory() as uow:
            pending = await uow.catalog_requests.list_pending(None)
            request_ids = [r.id for r in pending if r.id is not None]
            counts = await uow.catalog_subscriptions.count_by_requests(request_ids)

        return [
            AdminCatalogRequestItem(
                request=CatalogRequestOutput.from_entity(request, lang),
                subscriber_count=counts.get(request.id, 0),
            )
            for request in pending
        ]


__all__ = ["ListAdminCatalogRequestsUseCase"]
