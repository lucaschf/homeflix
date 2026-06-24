"""Unit test fixtures for the catalog_requests bounded context."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWork,
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.catalog_requests.domain.repositories import (
    CatalogRequestRepository,
    CatalogSubscriptionRepository,
)


@dataclass
class CatalogRequestsUoWMocks:
    """Bundle of mocks produced by ``make_catalog_requests_uow_mock``."""

    factory: CatalogRequestsUnitOfWorkFactory
    uow: CatalogRequestsUnitOfWork
    catalog_requests: AsyncMock
    catalog_subscriptions: AsyncMock


def make_catalog_requests_uow_mock() -> CatalogRequestsUoWMocks:
    """Build a mock :class:`CatalogRequestsUnitOfWork` factory."""
    catalog_requests = AsyncMock(spec=CatalogRequestRepository)

    catalog_subscriptions = AsyncMock(spec=CatalogSubscriptionRepository)
    # Sensible "nobody subscribed yet" defaults so the common paths
    # don't have to wire these up explicitly.
    catalog_subscriptions.find.return_value = None
    catalog_subscriptions.list_for_request.return_value = []
    catalog_subscriptions.count_for_request.return_value = 0
    catalog_subscriptions.count_by_requests.return_value = {}
    catalog_subscriptions.request_ids_for_user.return_value = set()
    catalog_subscriptions.remove.return_value = False

    uow: CatalogRequestsUnitOfWork = AsyncMock()
    uow.__aenter__.return_value = uow  # type: ignore[attr-defined]
    uow.__aexit__.return_value = None  # type: ignore[attr-defined]
    uow.catalog_requests = catalog_requests
    uow.catalog_subscriptions = catalog_subscriptions

    factory = MagicMock(return_value=uow)
    return CatalogRequestsUoWMocks(
        factory=factory,
        uow=uow,
        catalog_requests=catalog_requests,
        catalog_subscriptions=catalog_subscriptions,
    )
