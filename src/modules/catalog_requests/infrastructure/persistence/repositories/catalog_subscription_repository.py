"""SQLAlchemy implementation of ``CatalogSubscriptionRepository``."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.catalog_requests.domain.entities import CatalogSubscription
from src.modules.catalog_requests.domain.repositories import (
    CatalogSubscriptionRepository,
)
from src.modules.catalog_requests.domain.value_objects import CatalogRequestId
from src.modules.catalog_requests.infrastructure.persistence.mappers import (
    CatalogSubscriptionMapper,
)
from src.modules.catalog_requests.infrastructure.persistence.models import (
    CatalogSubscriptionModel,
)


class SQLAlchemyCatalogSubscriptionRepository(CatalogSubscriptionRepository):
    """SQLAlchemy implementation of ``CatalogSubscriptionRepository``.

    Example:
        >>> repo = SQLAlchemyCatalogSubscriptionRepository(session)
        >>> subs = await repo.list_for_request(request_id)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    async def add(self, subscription: CatalogSubscription) -> CatalogSubscription:
        """Persist a new subscription."""
        model = CatalogSubscriptionMapper.to_model(subscription)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return CatalogSubscriptionMapper.to_entity(model)

    async def find(
        self,
        request_id: CatalogRequestId,
        user_id: str,
    ) -> CatalogSubscription | None:
        """Look up a single subscription by its natural key."""
        stmt = select(CatalogSubscriptionModel).where(
            CatalogSubscriptionModel.request_id == str(request_id),
            CatalogSubscriptionModel.user_id == user_id,
            CatalogSubscriptionModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else CatalogSubscriptionMapper.to_entity(model)

    async def list_for_request(
        self,
        request_id: CatalogRequestId,
    ) -> list[CatalogSubscription]:
        """List every active subscription for a request (the fanout read)."""
        stmt = select(CatalogSubscriptionModel).where(
            CatalogSubscriptionModel.request_id == str(request_id),
            CatalogSubscriptionModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return [CatalogSubscriptionMapper.to_entity(m) for m in result.scalars().all()]

    async def remove(
        self,
        request_id: CatalogRequestId,
        user_id: str,
    ) -> bool:
        """Soft-delete a subscription by its natural key (unsubscribe)."""
        stmt = select(CatalogSubscriptionModel).where(
            CatalogSubscriptionModel.request_id == str(request_id),
            CatalogSubscriptionModel.user_id == user_id,
            CatalogSubscriptionModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        model.soft_delete()
        await self._session.flush()
        return True

    async def count_for_request(self, request_id: CatalogRequestId) -> int:
        """Count active subscribers for a single request."""
        stmt = (
            select(func.count())
            .select_from(CatalogSubscriptionModel)
            .where(
                CatalogSubscriptionModel.request_id == str(request_id),
                CatalogSubscriptionModel.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_by_requests(
        self,
        request_ids: Sequence[CatalogRequestId],
    ) -> dict[CatalogRequestId, int]:
        """Batch subscriber counts keyed by request."""
        if not request_ids:
            return {}
        keys = [str(rid) for rid in request_ids]
        stmt = (
            select(
                CatalogSubscriptionModel.request_id,
                func.count().label("n"),
            )
            .where(
                CatalogSubscriptionModel.request_id.in_(keys),
                CatalogSubscriptionModel.deleted_at.is_(None),
            )
            .group_by(CatalogSubscriptionModel.request_id)
        )
        result = await self._session.execute(stmt)
        return {CatalogRequestId(row.request_id): row.n for row in result.all()}

    async def request_ids_for_user(self, user_id: str) -> set[CatalogRequestId]:
        """Return the set of requests a user currently subscribes to."""
        stmt = (
            select(CatalogSubscriptionModel.request_id)
            .where(
                CatalogSubscriptionModel.user_id == user_id,
                CatalogSubscriptionModel.deleted_at.is_(None),
            )
            .distinct()
        )
        result = await self._session.execute(stmt)
        return {CatalogRequestId(rid) for rid in result.scalars().all()}


__all__ = ["SQLAlchemyCatalogSubscriptionRepository"]
