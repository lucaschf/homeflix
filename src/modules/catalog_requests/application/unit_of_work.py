"""Catalog Requests bounded-context Unit of Work interface."""

from abc import ABC, abstractmethod

from src.building_blocks.application.unit_of_work import UnitOfWork
from src.modules.catalog_requests.domain.repositories import (
    CatalogRequestRepository,
    CatalogSubscriptionRepository,
)


class CatalogRequestsUnitOfWork(UnitOfWork):
    """Transactional boundary for catalog-request writes."""

    catalog_requests: CatalogRequestRepository
    catalog_subscriptions: CatalogSubscriptionRepository


class CatalogRequestsUnitOfWorkFactory(ABC):
    """Builds fresh ``CatalogRequestsUnitOfWork`` instances on demand."""

    @abstractmethod
    def __call__(self) -> CatalogRequestsUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""


__all__ = ["CatalogRequestsUnitOfWork", "CatalogRequestsUnitOfWorkFactory"]
