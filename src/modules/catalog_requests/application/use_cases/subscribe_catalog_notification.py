"""Subscribe to the arrival notification for a TMDB title."""

from src.modules.catalog_requests.application.dtos import (
    CatalogRequestOutput,
    SubscribeCatalogNotificationInput,
)
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWork,
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.catalog_requests.domain.entities import (
    CatalogRequest,
    CatalogSubscription,
)
from src.modules.catalog_requests.domain.value_objects import CatalogRequestId


class SubscribeCatalogNotificationUseCase:
    """Idempotent "Avisar quando chegar" handler.

    Ensures the title's request row exists (creating it in the same
    call when the user clicks "Avisar quando chegar" without having
    clicked "Solicitar inclusão" first), then records a per-user
    ``CatalogSubscription`` so the arrival fanout reaches this user
    (ADR-022). ``notify_on_arrival`` is kept as a denormalized
    "has ≥1 subscriber" flag for the read-side CTA.

    Idempotent on both halves: a repeat call neither duplicates the
    request (keyed on ``(tmdb_id, media_type)``) nor the subscription
    (keyed on ``(request, user)``).

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
                # entry point always wants the notification flag on.
                reconciled = existing.reconcile(
                    title=input_dto.title,
                    requester_user_id=input_dto.requester_user_id,
                    notify=True,
                )
                request = (
                    existing
                    if reconciled is None
                    else await uow.catalog_requests.update(reconciled)
                )
            else:
                request = await uow.catalog_requests.add(
                    CatalogRequest.create(
                        tmdb_id=input_dto.tmdb_id,
                        media_type=input_dto.media_type,
                        title=input_dto.title,
                        requester_user_id=input_dto.requester_user_id,
                        collection_tmdb_id=input_dto.collection_tmdb_id,
                        notify_on_arrival=True,
                    ),
                )

            await self._ensure_subscription(uow, request.id, input_dto.requester_user_id)
            return CatalogRequestOutput.from_entity(request)

    @staticmethod
    async def _ensure_subscription(
        uow: CatalogRequestsUnitOfWork,
        request_id: CatalogRequestId | None,
        user_id: str | None,
    ) -> None:
        """Add a subscription for ``user_id`` unless one already exists.

        No-op for an anonymous call (``user_id`` is ``None``) — there
        is no inbox to fan out to, so only the denormalized
        ``notify_on_arrival`` flag carries that legacy intent.
        """
        if user_id is None or request_id is None:
            return
        if await uow.catalog_subscriptions.find(request_id, user_id) is None:
            await uow.catalog_subscriptions.add(
                CatalogSubscription.create(request_id=request_id, user_id=user_id),
            )


__all__ = ["SubscribeCatalogNotificationUseCase"]
