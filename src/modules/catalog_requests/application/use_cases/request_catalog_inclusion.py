"""Register a catalog inclusion request for a TMDB title."""

from src.modules.catalog_requests.application.dtos import (
    CatalogRequestOutput,
    CreateCatalogRequestInput,
)
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.catalog_requests.domain.entities import CatalogRequest


class RequestCatalogInclusionUseCase:
    """Idempotent "Solicitar inclusão" handler.

    Records the user's desire to have a TMDB title added to the
    catalog. The action is idempotent on ``(tmdb_id, media_type)``:
    repeated calls return the existing request rather than failing
    or creating duplicates, since the UI's optimistic state and a
    flaky network can both cause a re-submit.

    When the caller passes ``notify_on_arrival=True`` and an existing
    request still has notifications off, the use case flips it on
    so the same endpoint can be reused for the "request + notify"
    combo. When the existing request is already opted in, the
    second call short-circuits with no DB write.

    Example:
        >>> uc = RequestCatalogInclusionUseCase(uow_factory)
        >>> out = await uc.execute(CreateCatalogRequestInput(
        ...     tmdb_id=348,
        ...     media_type=RequestedMediaType.MOVIE,
        ...     collection_tmdb_id=8091,
        ... ))
        >>> out.tmdb_id
        348
    """

    def __init__(self, uow_factory: CatalogRequestsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh catalog-requests
                Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: CreateCatalogRequestInput) -> CatalogRequestOutput:
        """Execute the use case.

        Args:
            input_dto: Carries the TMDB target plus optional
                ``collection_tmdb_id`` and ``notify_on_arrival`` flag.

        Returns:
            The persisted (or pre-existing) request, serialized for
            API consumption.
        """
        async with self._uow_factory() as uow:
            existing = await uow.catalog_requests.find_by_tmdb_id(
                input_dto.tmdb_id,
                input_dto.media_type,
            )
            if existing is not None:
                # Repeat submit: flip the notify flag on if the caller
                # asked for it, and backfill the title when a legacy
                # row was created before the column existed. Either
                # write opens the same persisted path so the response
                # stays a single round-trip.
                title_backfill = (
                    input_dto.title if existing.title is None and input_dto.title else None
                )
                wants_notify = input_dto.notify_on_arrival and not existing.notify_on_arrival
                if title_backfill or wants_notify:
                    updates: dict[str, object] = {}
                    if title_backfill:
                        updates["title"] = title_backfill
                    if wants_notify:
                        updates["notify_on_arrival"] = True
                    updated = existing.with_updates(**updates)
                    persisted = await uow.catalog_requests.update(updated)
                    return CatalogRequestOutput.from_entity(persisted)
                return CatalogRequestOutput.from_entity(existing)

            request = CatalogRequest.create(
                tmdb_id=input_dto.tmdb_id,
                media_type=input_dto.media_type,
                title=input_dto.title,
                collection_tmdb_id=input_dto.collection_tmdb_id,
                notify_on_arrival=input_dto.notify_on_arrival,
            )
            persisted = await uow.catalog_requests.add(request)
            return CatalogRequestOutput.from_entity(persisted)


__all__ = ["RequestCatalogInclusionUseCase"]
