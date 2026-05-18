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
from src.shared_kernel.value_objects.profile_id import ProfileId


class SQLAlchemyWatchlistRepository(WatchlistRepository):
    """SQLAlchemy implementation of WatchlistRepository.

    Every read/delete query is scoped by ``profile_id`` so a profile
    only sees its own watchlist. ``add`` derives the profile from the
    entity, matching the contract.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_media_id(
        self,
        media_id: str,
        profile_id: ProfileId,
    ) -> WatchlistItem | None:
        """Find a row scoped to ``(media_id, profile_id)``."""
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.media_id == media_id,
            WatchlistItemModel.profile_id == str(profile_id),
            WatchlistItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else WatchlistItemMapper.to_entity(model)

    async def add(self, item: WatchlistItem) -> WatchlistItem:
        """Add an item to the watchlist.

        If a soft-deleted record exists for the same
        ``(profile_id, media_id)`` pair, restore it instead of
        creating a duplicate (otherwise the composite UNIQUE
        constraint would refuse the insert).
        """
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.media_id == item.media_id,
            WatchlistItemModel.profile_id == str(item.profile_id),
            WatchlistItemModel.deleted_at.is_not(None),
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.restore()
            WatchlistItemMapper.update_model(existing, item)
            await self._session.flush()
            await self._session.refresh(existing)
            return WatchlistItemMapper.to_entity(existing)

        model = WatchlistItemMapper.to_model(item)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return WatchlistItemMapper.to_entity(model)

    async def remove(self, media_id: str, profile_id: ProfileId) -> bool:
        """Soft-delete the row for (media_id, profile_id)."""
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.media_id == media_id,
            WatchlistItemModel.profile_id == str(profile_id),
            WatchlistItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        model.soft_delete()
        await self._session.flush()
        return True

    async def list_all(
        self,
        profile_id: ProfileId,
        limit: int = 100,
    ) -> list[WatchlistItem]:
        """List the profile's watchlist entries ordered by most recently added."""
        stmt = (
            select(WatchlistItemModel)
            .where(
                WatchlistItemModel.profile_id == str(profile_id),
                WatchlistItemModel.deleted_at.is_(None),
            )
            .order_by(WatchlistItemModel.added_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [WatchlistItemMapper.to_entity(m) for m in result.scalars().all()]

    async def exists(self, media_id: str, profile_id: ProfileId) -> bool:
        """Check whether ``media_id`` is on ``profile_id``'s watchlist."""
        stmt = (
            select(func.count())
            .select_from(WatchlistItemModel)
            .where(
                WatchlistItemModel.media_id == media_id,
                WatchlistItemModel.profile_id == str(profile_id),
                WatchlistItemModel.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return (result.scalar() or 0) > 0

    async def delete_all_for_profiles(self, profile_ids: list[str]) -> int:
        """Soft-delete every watchlist row owned by the given profiles."""
        if not profile_ids:
            return 0
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.profile_id.in_(profile_ids),
            WatchlistItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            model.soft_delete()
        if models:
            await self._session.flush()
        return len(models)

    async def rewrite_media_id(
        self,
        from_media_id: str,
        to_media_id: str,
        to_media_type: str,
    ) -> int:
        """Repoint every watchlist row (across profiles) to a new media id."""
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.media_id == from_media_id,
            WatchlistItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            model.media_id = to_media_id
            model.media_type = to_media_type
        if models:
            await self._session.flush()
        return len(models)


__all__ = ["SQLAlchemyWatchlistRepository"]
