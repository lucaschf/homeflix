"""List pending catalog requests."""

from dataclasses import dataclass

from src.modules.catalog_requests.application.dtos import CatalogRequestOutput
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWorkFactory,
)


@dataclass(frozen=True)
class ListCatalogRequestsInput:
    """Input for ``ListCatalogRequestsUseCase``.

    Attributes:
        collection_tmdb_id: When supplied, scope the listing to a
            single TMDB collection — useful for the Collection
            Detail "X pending in this saga" rollup.
    """

    collection_tmdb_id: int | None = None


class ListCatalogRequestsUseCase:
    """Return all pending catalog requests, optionally scoped to a saga.

    Pending = ``fulfilled_at IS NULL``. The catalog-acquisition
    workflow (or a future admin panel) consumes this list to know
    what titles to track down.
    """

    def __init__(self, uow_factory: CatalogRequestsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh catalog-requests
                Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(
        self,
        input_dto: ListCatalogRequestsInput | None = None,
    ) -> list[CatalogRequestOutput]:
        """Execute the use case.

        Args:
            input_dto: Optional filter input. ``None`` returns all
                pending requests across every collection.

        Returns:
            Pending requests serialized for API consumption.
        """
        scope = input_dto.collection_tmdb_id if input_dto is not None else None
        async with self._uow_factory() as uow:
            pending = await uow.catalog_requests.list_pending(scope)
        return [CatalogRequestOutput.from_entity(r) for r in pending]


__all__ = ["ListCatalogRequestsInput", "ListCatalogRequestsUseCase"]
