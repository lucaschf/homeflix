"""List pending catalog requests enriched for the member 'Em breve' feed."""

from dataclasses import dataclass
from typing import cast

from src.modules.catalog_requests.application.dtos import (
    CatalogRequestFeedItem,
    CatalogRequestOutput,
)
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.catalog_requests.domain.value_objects import CatalogRequestId


@dataclass(frozen=True)
class ListCatalogRequestFeedInput:
    """Input for ``ListCatalogRequestFeedUseCase``.

    Attributes:
        user_id: External id (``usr_xxx``) of the caller, so each item
            can carry whether *this* user is subscribed.
        collection_tmdb_id: Optional franchise scope (same filter as
            the plain listing).
    """

    user_id: str
    collection_tmdb_id: int | None = None
    lang: str = "en"


class ListCatalogRequestFeedUseCase:
    """Pending requests + per-caller subscription state for "Em breve".

    The member-facing view behind the consumer page: every pending
    title, each annotated with its active subscriber count and whether
    the calling user follows it (ADR-022). Counts and the caller's
    subscriptions are resolved in two batch queries rather than N+1.
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
        input_dto: ListCatalogRequestFeedInput,
    ) -> list[CatalogRequestFeedItem]:
        """Execute the use case.

        Returns:
            Pending requests enriched with ``subscriber_count`` and the
            caller's ``is_subscribed`` flag, newest first.
        """
        async with self._uow_factory() as uow:
            pending = await uow.catalog_requests.list_pending(
                input_dto.collection_tmdb_id,
            )
            request_ids = [r.id for r in pending if r.id is not None]
            counts = await uow.catalog_subscriptions.count_by_requests(request_ids)
            subscribed = await uow.catalog_subscriptions.request_ids_for_user(
                input_dto.user_id,
            )

        return [
            CatalogRequestFeedItem(
                request=CatalogRequestOutput.from_entity(request, input_dto.lang),
                subscriber_count=counts.get(cast(CatalogRequestId, request.id), 0),
                is_subscribed=request.id in subscribed,
            )
            for request in pending
        ]


__all__ = ["ListCatalogRequestFeedInput", "ListCatalogRequestFeedUseCase"]
