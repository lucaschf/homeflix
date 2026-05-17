"""SQLAlchemy implementation of ``CatalogRequestRepository``."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.modules.catalog_requests.domain.repositories import CatalogRequestRepository
from src.modules.catalog_requests.domain.value_objects import (
    CatalogRequestId,
    RequestedMediaType,
)
from src.modules.catalog_requests.infrastructure.persistence.mappers import (
    CatalogRequestMapper,
)
from src.modules.catalog_requests.infrastructure.persistence.models import (
    CatalogRequestModel,
)


class SQLAlchemyCatalogRequestRepository(CatalogRequestRepository):
    """SQLAlchemy implementation of ``CatalogRequestRepository``.

    Example:
        >>> repo = SQLAlchemyCatalogRequestRepository(session)
        >>> req = await repo.find_by_tmdb_id(348, RequestedMediaType.MOVIE)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    async def find_by_tmdb_id(
        self,
        tmdb_id: int,
        media_type: RequestedMediaType,
    ) -> CatalogRequest | None:
        """Look up a single request by its TMDB target."""
        stmt = select(CatalogRequestModel).where(
            CatalogRequestModel.tmdb_id == tmdb_id,
            CatalogRequestModel.media_type == media_type.value,
            CatalogRequestModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else CatalogRequestMapper.to_entity(model)

    async def find_by_tmdb_ids(
        self,
        tmdb_ids: Sequence[int],
        media_type: RequestedMediaType,
    ) -> dict[int, CatalogRequest]:
        """Batch lookup keyed by TMDB id."""
        if not tmdb_ids:
            return {}
        stmt = select(CatalogRequestModel).where(
            CatalogRequestModel.tmdb_id.in_(list(tmdb_ids)),
            CatalogRequestModel.media_type == media_type.value,
            CatalogRequestModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return {m.tmdb_id: CatalogRequestMapper.to_entity(m) for m in models}

    async def list_pending(
        self,
        collection_tmdb_id: int | None = None,
    ) -> list[CatalogRequest]:
        """List unfulfilled requests, optionally scoped to a franchise."""
        stmt = (
            select(CatalogRequestModel)
            .where(
                CatalogRequestModel.fulfilled_at.is_(None),
                CatalogRequestModel.deleted_at.is_(None),
            )
            .order_by(CatalogRequestModel.requested_at.desc())
        )
        if collection_tmdb_id is not None:
            stmt = stmt.where(CatalogRequestModel.collection_tmdb_id == collection_tmdb_id)
        result = await self._session.execute(stmt)
        return [CatalogRequestMapper.to_entity(m) for m in result.scalars().all()]

    async def add(self, request: CatalogRequest) -> CatalogRequest:
        """Persist a new request."""
        model = CatalogRequestMapper.to_model(request)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return CatalogRequestMapper.to_entity(model)

    async def update(self, request: CatalogRequest) -> CatalogRequest:
        """Update an existing request."""
        stmt = select(CatalogRequestModel).where(
            CatalogRequestModel.external_id == str(request.id),
            CatalogRequestModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            msg = f"CatalogRequest {request.id} not found for update"
            raise ValueError(msg)

        CatalogRequestMapper.update_model(model, request)
        await self._session.flush()
        await self._session.refresh(model)
        return CatalogRequestMapper.to_entity(model)

    async def delete(self, request_id: CatalogRequestId) -> bool:
        """Soft-delete a pending request by external id."""
        stmt = select(CatalogRequestModel).where(
            CatalogRequestModel.external_id == str(request_id),
            CatalogRequestModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        model.soft_delete()
        await self._session.flush()
        return True


__all__ = ["SQLAlchemyCatalogRequestRepository"]
