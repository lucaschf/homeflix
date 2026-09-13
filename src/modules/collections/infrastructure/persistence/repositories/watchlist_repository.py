"""SQLAlchemy implementation of WatchlistRepository."""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.repositories import (
    WatchlistCursor,
    WatchlistPage,
    WatchlistRepository,
)
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.modules.collections.infrastructure.persistence.mappers import (
    WatchlistItemMapper,
)
from src.modules.collections.infrastructure.persistence.models import (
    WatchlistItemModel,
)
from src.shared_kernel.value_objects import MediaType
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
        media_id: CollectionMediaId,
        profile_id: ProfileId,
    ) -> WatchlistItem | None:
        """Find a row scoped to ``(media_id, profile_id)``."""
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.media_id == media_id.value,
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
            WatchlistItemModel.media_id == item.media_id.value,
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

    async def remove(self, media_id: CollectionMediaId, profile_id: ProfileId) -> bool:
        """Soft-delete the row for (media_id, profile_id)."""
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.media_id == media_id.value,
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

    async def list_page(
        self,
        profile_id: ProfileId,
        *,
        limit: int,
        after: WatchlistCursor | None,
    ) -> WatchlistPage:
        """Read one keyset page of the profile's watchlist, most recently added first.

        The cursor is bound through the ``added_at`` column type, so it is
        rendered in the same text form SQLite stores and the comparison
        stays chronological.
        """
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.profile_id == str(profile_id),
            WatchlistItemModel.deleted_at.is_(None),
        )
        if after is not None:
            stmt = stmt.where(
                or_(
                    WatchlistItemModel.added_at < after.added_at,
                    and_(
                        WatchlistItemModel.added_at == after.added_at,
                        WatchlistItemModel.media_id < after.media_id,
                    ),
                )
            )
        stmt = stmt.order_by(
            WatchlistItemModel.added_at.desc(),
            WatchlistItemModel.media_id.desc(),
        ).limit(limit)
        result = await self._session.execute(stmt)
        models = list(result.scalars().all())

        next_cursor = (
            WatchlistCursor(added_at=models[-1].added_at, media_id=models[-1].media_id)
            if models and len(models) >= limit
            else None
        )
        return WatchlistPage(
            items=[WatchlistItemMapper.to_entity(m) for m in models],
            next_cursor=next_cursor,
        )

    async def exists(self, media_id: CollectionMediaId, profile_id: ProfileId) -> bool:
        """Check whether ``media_id`` is on ``profile_id``'s watchlist."""
        stmt = (
            select(func.count())
            .select_from(WatchlistItemModel)
            .where(
                WatchlistItemModel.media_id == media_id.value,
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
        from_media_id: CollectionMediaId,
        to_media_id: CollectionMediaId,
        to_media_type: MediaType,
    ) -> int:
        """Repoint every watchlist row (across profiles) to a new media id."""
        stmt = select(WatchlistItemModel).where(
            WatchlistItemModel.media_id == from_media_id.value,
            WatchlistItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            model.media_id = to_media_id.value
            model.media_type = to_media_type.value
        if models:
            await self._session.flush()
        return len(models)


__all__ = ["SQLAlchemyWatchlistRepository"]
