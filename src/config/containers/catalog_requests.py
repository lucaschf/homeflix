"""Catalog Requests bounded context dependency container."""

from typing import Any

from dependency_injector import containers, providers

from src.modules.catalog_requests.application.use_cases import (
    DismissCatalogRequestUseCase,
    IncludeCatalogRequestUseCase,
    ListAdminCatalogRequestsUseCase,
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


class CatalogRequestsContainer(containers.DeclarativeContainer):
    """Container for the Catalog Requests bounded context.

    Exposes:
        - The ``CatalogRequestsUnitOfWorkFactory`` so use cases inside
          this BC open transactions.
        - A ``CatalogRequestLookupAdapter`` factory the Media BC
          consumes via its ``CatalogRequestLookupPort`` (ADR-009).
        - Use case providers wired into the ``/catalog-requests``
          REST routes.
    """

    session_factory = providers.Dependency[Any]()

    # Cross-BC publisher (Notifications BC) — powers the arrival fanout
    # on the manual "mark as included" action (ADR-022 / ADR-009).
    notification_publisher = providers.Dependency[Any]()

    # Cross-BC title provider (Media BC / TMDB) — resolves the
    # per-language title snapshot at request-creation time. Wired at
    # the composition root so this BC takes no Media dependency.
    localized_title_provider = providers.Dependency[Any]()

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
        localized_title_provider=localized_title_provider,
    )

    subscribe_catalog_notification = providers.Factory(
        SubscribeCatalogNotificationUseCase,
        uow_factory=catalog_requests_unit_of_work_factory,
        localized_title_provider=localized_title_provider,
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

    list_admin_catalog_requests = providers.Factory(
        ListAdminCatalogRequestsUseCase,
        uow_factory=catalog_requests_unit_of_work_factory,
    )

    dismiss_catalog_request = providers.Factory(
        DismissCatalogRequestUseCase,
        uow_factory=catalog_requests_unit_of_work_factory,
    )

    include_catalog_request = providers.Factory(
        IncludeCatalogRequestUseCase,
        uow_factory=catalog_requests_unit_of_work_factory,
        notification_publisher=notification_publisher,
    )
