"""Register a catalog inclusion request for a TMDB title."""

from src.modules.catalog_requests.application.dtos import (
    CatalogRequestOutput,
    CreateCatalogRequestInput,
)
from src.modules.catalog_requests.application.ports import LocalizedTitleProviderPort
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.catalog_requests.application.use_cases._localized_title_helpers import (
    resolve_localized_titles,
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
        ...     media_type=MediaType.MOVIE,
        ...     collection_tmdb_id=8091,
        ... ))
        >>> out.tmdb_id
        348
    """

    def __init__(
        self,
        uow_factory: CatalogRequestsUnitOfWorkFactory,
        localized_title_provider: LocalizedTitleProviderPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh catalog-requests
                Unit of Work.
            localized_title_provider: Cross-BC port that resolves the
                per-language TMDB title snapshot at creation time.
        """
        self._uow_factory = uow_factory
        self._titles = localized_title_provider

    async def execute(self, input_dto: CreateCatalogRequestInput) -> CatalogRequestOutput:
        """Execute the use case.

        Resolves the per-language title snapshot from TMDB **outside**
        the write transaction (a single ``/translations`` round-trip),
        so the DB write never holds a lock open during network I/O. The
        existence check runs twice — once to decide whether a fetch is
        even needed, once inside the write transaction to stay
        idempotent on ``(tmdb_id, media_type)``.

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

        # Only pay the TMDB round-trip when there's no localized snapshot
        # yet (new request, or a legacy row that predates this column).
        need_titles = existing is None or not existing.localized_titles
        localized_titles = (
            await resolve_localized_titles(self._titles, input_dto.tmdb_id, input_dto.media_type)
            if need_titles
            else {}
        )

        async with self._uow_factory() as uow:
            existing = await uow.catalog_requests.find_by_tmdb_id(
                input_dto.tmdb_id,
                input_dto.media_type,
            )
            if existing is not None:
                # Repeat submit: let the aggregate fold in the new data
                # (first-owner-wins backfill + one-way notify opt-in).
                # ``None`` means nothing changed, so skip the write.
                reconciled = existing.reconcile(
                    title=input_dto.title,
                    poster_url=input_dto.poster_url,
                    requester_user_id=input_dto.requester_user_id,
                    notify=input_dto.notify_on_arrival,
                    localized_titles=localized_titles,
                )
                if reconciled is None:
                    return CatalogRequestOutput.from_entity(existing)
                persisted = await uow.catalog_requests.update(reconciled)
                return CatalogRequestOutput.from_entity(persisted)

            request = CatalogRequest.create(
                tmdb_id=input_dto.tmdb_id,
                media_type=input_dto.media_type,
                title=input_dto.title,
                poster_url=input_dto.poster_url,
                requester_user_id=input_dto.requester_user_id,
                collection_tmdb_id=input_dto.collection_tmdb_id,
                notify_on_arrival=input_dto.notify_on_arrival,
                localized_titles=localized_titles,
            )
            persisted = await uow.catalog_requests.add(request)
            return CatalogRequestOutput.from_entity(persisted)


__all__ = ["RequestCatalogInclusionUseCase"]
