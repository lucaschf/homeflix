"""Unsubscribe a user from a TMDB title's arrival notification."""

from src.modules.catalog_requests.application.dtos import (
    CatalogRequestOutput,
    UnsubscribeCatalogNotificationInput,
)
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWorkFactory,
)


class UnsubscribeCatalogNotificationUseCase:
    """Idempotent "desligar o aviso" handler (ADR-022).

    Drops the acting user's ``CatalogSubscription`` for a title and
    leaves the request — and every other subscriber — untouched: the
    queue tracks titles, not interest, so it survives with zero
    subscribers. The denormalized ``notify_on_arrival`` flag on the
    request is recomputed from the remaining live subscriber count so
    the read-side CTA stays accurate.

    No request for the title, or no subscription for the user, is not
    an error — both return the current state (or ``None``) so a
    double-tap on "desligar" is harmless.

    Example:
        >>> uc = UnsubscribeCatalogNotificationUseCase(uow_factory)
        >>> await uc.execute(UnsubscribeCatalogNotificationInput(
        ...     tmdb_id=348,
        ...     media_type=MediaType.MOVIE,
        ...     user_id="usr_alice",
        ... ))
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
        input_dto: UnsubscribeCatalogNotificationInput,
    ) -> CatalogRequestOutput | None:
        """Execute the use case.

        Returns:
            The request with its refreshed ``notify_on_arrival`` flag,
            or ``None`` when no request exists for the title.
        """
        async with self._uow_factory() as uow:
            request = await uow.catalog_requests.find_by_tmdb_id(
                input_dto.tmdb_id,
                input_dto.media_type,
            )
            if request is None or request.id is None:
                return None

            await uow.catalog_subscriptions.remove(request.id, input_dto.user_id)

            # Re-derive the "has ≥1 subscriber" flag from the live count
            # so the read-side CTA reflects reality after the drop.
            remaining = await uow.catalog_subscriptions.count_for_request(request.id)
            has_subscribers = remaining > 0
            if request.notify_on_arrival != has_subscribers:
                request = await uow.catalog_requests.update(
                    request.enable_notification()
                    if has_subscribers
                    else request.disable_notification(),
                )

            return CatalogRequestOutput.from_entity(request)


__all__ = ["UnsubscribeCatalogNotificationUseCase"]
