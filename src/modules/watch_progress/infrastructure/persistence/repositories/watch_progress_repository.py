"""SQLAlchemy implementation of WatchProgressRepository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.repositories import WatchProgressRepository
from src.modules.watch_progress.infrastructure.persistence.mappers import (
    WatchProgressMapper,
)
from src.modules.watch_progress.infrastructure.persistence.models import (
    WatchProgressModel,
)


class SQLAlchemyWatchProgressRepository(WatchProgressRepository):
    """SQLAlchemy implementation of WatchProgressRepository.

    Example:
        >>> repo = SQLAlchemyWatchProgressRepository(session)
        >>> progress = await repo.find_by_media_id("mov_abc123def456")
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    async def find_by_media_id(self, media_id: str) -> WatchProgress | None:
        """Find progress by media external ID."""
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.media_id == media_id,
            WatchProgressModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else WatchProgressMapper.to_entity(model)

    async def save(self, progress: WatchProgress) -> WatchProgress:
        """Create or update a watch progress record."""
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.media_id == progress.media_id,
            WatchProgressModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            WatchProgressMapper.update_model(existing, progress)
            await self._session.commit()
            await self._session.refresh(existing)
            return WatchProgressMapper.to_entity(existing)

        model = WatchProgressMapper.to_model(progress)
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return WatchProgressMapper.to_entity(model)

    async def list_in_progress(self, limit: int = 20) -> list[WatchProgress]:
        """List in-progress items ordered by last watched."""
        stmt = (
            select(WatchProgressModel)
            .where(
                WatchProgressModel.status == "in_progress",
                WatchProgressModel.deleted_at.is_(None),
            )
            .order_by(WatchProgressModel.last_watched_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [WatchProgressMapper.to_entity(m) for m in result.scalars().all()]

    async def list_recently_watched(self, limit: int = 20) -> list[WatchProgress]:
        """List recently watched items (in_progress + completed)."""
        stmt = (
            select(WatchProgressModel)
            .where(
                WatchProgressModel.status.in_(["in_progress", "completed"]),
                WatchProgressModel.deleted_at.is_(None),
            )
            .order_by(WatchProgressModel.last_watched_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [WatchProgressMapper.to_entity(m) for m in result.scalars().all()]

    async def find_by_media_ids(self, media_ids: list[str]) -> dict[str, WatchProgress]:
        """Find progress for multiple media items in a single query."""
        if not media_ids:
            return {}
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.media_id.in_(media_ids),
            WatchProgressModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return {m.media_id: WatchProgressMapper.to_entity(m) for m in result.scalars().all()}

    async def delete(self, media_id: str) -> bool:
        """Soft-delete progress for a media item."""
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.media_id == media_id,
            WatchProgressModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        model.soft_delete()
        await self._session.commit()
        return True


__all__ = ["SQLAlchemyWatchProgressRepository"]
