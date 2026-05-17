"""DismissCatalogRequestUseCase — admin removes a pending request."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.catalog_requests.application.dtos import DismissCatalogRequestInput
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.catalog_requests.domain.value_objects import CatalogRequestId


class DismissCatalogRequestUseCase:
    """Soft-delete a catalog request by its external id.

    Driven by the admin "Catalog requests" page — the operator
    drops a pending request the household no longer wants tracked.
    Soft-delete keeps the row recoverable via direct DB intervention
    (matches every other aggregate in the codebase) but list queries
    skip it from this point on.
    """

    def __init__(self, uow_factory: CatalogRequestsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: DismissCatalogRequestInput) -> None:
        """Soft-delete the request, or raise when nothing matches."""
        request_id = CatalogRequestId(input_dto.request_id)
        async with self._uow_factory() as uow:
            deleted = await uow.catalog_requests.delete(request_id)

        if not deleted:
            raise ResourceNotFoundException.for_resource("CatalogRequest", input_dto.request_id)


__all__ = ["DismissCatalogRequestUseCase"]
