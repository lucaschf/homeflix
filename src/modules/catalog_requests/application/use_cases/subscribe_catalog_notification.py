"""Subscribe to the arrival notification for a TMDB title."""

from src.modules.catalog_requests.application.dtos import (
    CatalogRequestOutput,
    SubscribeCatalogNotificationInput,
)
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.catalog_requests.domain.entities import CatalogRequest


class SubscribeCatalogNotificationUseCase:
    """Idempotent "Avisar quando chegar" handler.

    Sets ``notify_on_arrival=True`` on an existing request, or
    creates one in the same call when the user clicks "Avisar
    quando chegar" without having clicked "Solicitar inclusão"
    first. Either entry point produces the same end state, which
    is what the UI assumes when it renders the two buttons side
    by side on the missing-from-catalog FilmRow.

    Example:
        >>> uc = SubscribeCatalogNotificationUseCase(uow_factory)
        >>> out = await uc.execute(SubscribeCatalogNotificationInput(
        ...     tmdb_id=348,
        ...     media_type=MediaType.MOVIE,
        ... ))
        >>> out.notify_on_arrival
        True
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
        input_dto: SubscribeCatalogNotificationInput,
    ) -> CatalogRequestOutput:
        """Execute the use case.

        Returns:
            The persisted request with ``notify_on_arrival=True``.
        """
        async with self._uow_factory() as uow:
            existing = await uow.catalog_requests.find_by_tmdb_id(
                input_dto.tmdb_id,
                input_dto.media_type,
            )
            if existing is not None:
                # Same merge as the "Solicitar inclusão" path, but this
                # entry point always wants the notification on.
                reconciled = existing.reconcile(
                    title=input_dto.title,
                    requester_user_id=input_dto.requester_user_id,
                    notify=True,
                )
                if reconciled is None:
                    return CatalogRequestOutput.from_entity(existing)
                persisted = await uow.catalog_requests.update(reconciled)
                return CatalogRequestOutput.from_entity(persisted)

            request = CatalogRequest.create(
                tmdb_id=input_dto.tmdb_id,
                media_type=input_dto.media_type,
                title=input_dto.title,
                requester_user_id=input_dto.requester_user_id,
                collection_tmdb_id=input_dto.collection_tmdb_id,
                notify_on_arrival=True,
            )
            persisted = await uow.catalog_requests.add(request)
            return CatalogRequestOutput.from_entity(persisted)


__all__ = ["SubscribeCatalogNotificationUseCase"]
