"""Unit test fixtures for the catalog_requests bounded context."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWork,
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.catalog_requests.domain.repositories import CatalogRequestRepository


@dataclass
class CatalogRequestsUoWMocks:
    """Bundle of mocks produced by ``make_catalog_requests_uow_mock``."""

    factory: CatalogRequestsUnitOfWorkFactory
    uow: CatalogRequestsUnitOfWork
    catalog_requests: AsyncMock


def make_catalog_requests_uow_mock() -> CatalogRequestsUoWMocks:
    """Build a mock :class:`CatalogRequestsUnitOfWork` factory."""
    catalog_requests = AsyncMock(spec=CatalogRequestRepository)

    uow: CatalogRequestsUnitOfWork = AsyncMock()
    uow.__aenter__.return_value = uow  # type: ignore[attr-defined]
    uow.__aexit__.return_value = None  # type: ignore[attr-defined]
    uow.catalog_requests = catalog_requests

    factory = MagicMock(return_value=uow)
    return CatalogRequestsUoWMocks(
        factory=factory,
        uow=uow,
        catalog_requests=catalog_requests,
    )
