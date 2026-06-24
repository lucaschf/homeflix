"""Catalog Requests bounded context dependency container."""

from dependency_injector import containers, providers

from src.modules.catalog_requests.application.use_cases import (
    DismissCatalogRequestUseCase,
    ListCatalogRequestFeedUseCase,
    ListCatalogRequestsUseCase,
    RequestCatalogInclusionUseCase,
    SubscribeCatalogNotificationUseCase,
    UnsubscribeCatalogNotificationUseCase,
)
from src.modules.catalog_requests.infrastructure.acl import CatalogRequestLookupAdapter
from src.modules.catalog_requests.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyCatalogRequestsUnitOfWorkFactory,
)


class CatalogRequestsContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for the Catalog Requests bounded context.

    Exposes:
        - The ``CatalogRequestsUnitOfWorkFactory`` so use cases inside
          this BC open transactions.
        - A ``CatalogRequestLookupAdapter`` factory the Media BC
          consumes via its ``CatalogRequestLookupPort`` (ADR-009).
        - Use case providers wired into the ``/catalog-requests``
          REST routes.
    """

    session_factory = providers.Dependency()

    # =========================================================================
    # Unit of Work
    # =========================================================================

    catalog_requests_unit_of_work_factory = providers.Singleton(
        SqlAlchemyCatalogRequestsUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # =========================================================================
    # Anti-corruption layer (cross-BC read port adapter)
    # =========================================================================

    catalog_request_lookup = providers.Factory(
        CatalogRequestLookupAdapter,
        uow_factory=catalog_requests_unit_of_work_factory,
    )

    # =========================================================================
    # Use Cases
    # =========================================================================

    request_catalog_inclusion = providers.Factory(
        RequestCatalogInclusionUseCase,
        uow_factory=catalog_requests_unit_of_work_factory,
    )

    subscribe_catalog_notification = providers.Factory(
        SubscribeCatalogNotificationUseCase,
        uow_factory=catalog_requests_unit_of_work_factory,
    )

    unsubscribe_catalog_notification = providers.Factory(
        UnsubscribeCatalogNotificationUseCase,
        uow_factory=catalog_requests_unit_of_work_factory,
    )

    list_catalog_requests = providers.Factory(
        ListCatalogRequestsUseCase,
        uow_factory=catalog_requests_unit_of_work_factory,
    )

    list_catalog_request_feed = providers.Factory(
        ListCatalogRequestFeedUseCase,
        uow_factory=catalog_requests_unit_of_work_factory,
    )

    dismiss_catalog_request = providers.Factory(
        DismissCatalogRequestUseCase,
        uow_factory=catalog_requests_unit_of_work_factory,
    )
