"""SQLAlchemy implementation of WatchlistRepository."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.repositories import WatchlistRepository
from src.modules.collections.infrastructure.persistence.mappers import (
    WatchlistItemMapper,
)
from src.modules.collections.infrastructure.persistence.models import (
    WatchlistItemModel,
)


class SQLAlchemyWatchlistRepository(WatchlistRepository):
    """SQLAlchemy implementation of WatchlistRepository.

    Example:
        >>> repo = SQLAlchemyWatchlistRepository(session)
        >>> item = await repo.find_by_media_id("mov_abc123def456")
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    async def find_by_media_id(self, media_id: str) -> WatchlistItem | None:
        """Find a watchlist item by media external ID."""
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.media_id == media_id,
            WatchlistItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else WatchlistItemMapper.to_entity(model)

    async def add(self, item: WatchlistItem) -> WatchlistItem:
        """Add an item to the watchlist."""
        model = WatchlistItemMapper.to_model(item)
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return WatchlistItemMapper.to_entity(model)

    async def remove(self, media_id: str) -> bool:
        """Soft-delete an item from the watchlist."""
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.media_id == media_id,
            WatchlistItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        model.soft_delete()
        await self._session.commit()
        return True

    async def list_all(self, limit: int = 100) -> list[WatchlistItem]:
        """List all watchlist items ordered by most recently added."""
        stmt = (
            select(WatchlistItemModel)
            .where(WatchlistItemModel.deleted_at.is_(None))
            .order_by(WatchlistItemModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [WatchlistItemMapper.to_entity(m) for m in result.scalars().all()]

    async def exists(self, media_id: str) -> bool:
        """Check if a media item is in the watchlist."""
        stmt = (
            select(func.count())
            .select_from(WatchlistItemModel)
            .where(
                WatchlistItemModel.media_id == media_id,
                WatchlistItemModel.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return (result.scalar() or 0) > 0


__all__ = ["SQLAlchemyWatchlistRepository"]
