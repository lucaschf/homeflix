"""SQLAlchemy implementation of WatchProgressRepository."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.repositories import WatchProgressRepository
from src.modules.watch_progress.domain.value_objects import WatchableMediaId
from src.modules.watch_progress.infrastructure.persistence.mappers import (
    WatchProgressMapper,
)
from src.modules.watch_progress.infrastructure.persistence.models import (
    WatchProgressModel,
)
from src.shared_kernel.value_objects.episode_composite_id import EpisodeCompositeId
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId
from src.shared_kernel.value_objects.profile_id import ProfileId

_logger = logging.getLogger(__name__)


class SQLAlchemyWatchProgressRepository(WatchProgressRepository):
    """SQLAlchemy implementation of WatchProgressRepository.

    Every query is scoped by ``profile_id`` so rows from one profile
    never leak into another profile's view. The soft-delete-aware
    ``save`` lookup also matches on ``profile_id`` to avoid colliding
    with the composite ``(profile_id, media_id)`` unique constraint
    when a previously dismissed item is resumed.

    Example:
        >>> repo = SQLAlchemyWatchProgressRepository(session)
        >>> progress = await repo.find_by_media_id(
        ...     WatchableMediaId("mov_abc123def456"), caller_profile_id
        ... )
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_media_id(
        self,
        media_id: WatchableMediaId,
        profile_id: ProfileId,
    ) -> WatchProgress | None:
        """Look up a non-deleted row scoped to ``(media_id, profile_id)``."""
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.media_id == media_id.value,
            WatchProgressModel.profile_id == str(profile_id),
            WatchProgressModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else WatchProgressMapper.to_entity(model)

    async def save(self, progress: WatchProgress) -> WatchProgress:
        """Create or update a watch progress record.

        Looks up by (profile_id, media_id) including soft-deleted rows
        so resuming a previously dismissed item reuses the original
        row instead of colliding with the UNIQUE(profile_id, media_id)
        index.
        """
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.media_id == progress.media_id.value,
            WatchProgressModel.profile_id == str(progress.profile_id),
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            WatchProgressMapper.update_model(existing, progress)
            existing.restore()
            await self._session.flush()
            await self._session.refresh(existing)
            return WatchProgressMapper.to_entity(existing)

        model = WatchProgressMapper.to_model(progress)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return WatchProgressMapper.to_entity(model)

    async def list_in_progress(
        self,
        profile_id: ProfileId,
        limit: int = 20,
    ) -> list[WatchProgress]:
        """List in-progress rows for the profile, ordered by last watched."""
        stmt = (
            select(WatchProgressModel)
            .where(
                WatchProgressModel.profile_id == str(profile_id),
                WatchProgressModel.status == "in_progress",
                WatchProgressModel.deleted_at.is_(None),
            )
            .order_by(WatchProgressModel.last_watched_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return self._to_entities_dropping_invalid(result.scalars().all())

    async def list_recently_watched(
        self,
        profile_id: ProfileId,
        limit: int = 20,
    ) -> list[WatchProgress]:
        """List in-progress + completed rows for the profile, recent first."""
        stmt = (
            select(WatchProgressModel)
            .where(
                WatchProgressModel.profile_id == str(profile_id),
                WatchProgressModel.status.in_(["in_progress", "completed"]),
                WatchProgressModel.deleted_at.is_(None),
            )
            .order_by(WatchProgressModel.last_watched_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return self._to_entities_dropping_invalid(result.scalars().all())

    @staticmethod
    def _to_entities_dropping_invalid(
        models: list[WatchProgressModel],
    ) -> list[WatchProgress]:
        """Map rows to entities, dropping (and logging) corrupt media ids.

        Rows persisted before media-id validation existed may carry a
        ``media_id`` that no longer parses as :class:`WatchableMediaId`.
        Such rows were already invisible downstream (Continue Watching
        silently skipped them); dropping them here with a WARNING makes
        the corrupt state observable instead of silent.
        """
        entities: list[WatchProgress] = []
        for model in models:
            try:
                entities.append(WatchProgressMapper.to_entity(model))
            except DomainValidationException:
                _logger.warning(
                    "Dropping watch-progress row %s with invalid media_id %r",
                    model.id,
                    model.media_id,
                )
        return entities

    async def find_by_media_ids(
        self,
        media_ids: list[WatchableMediaId],
        profile_id: ProfileId,
    ) -> dict[str, WatchProgress]:
        """Bulk-look-up rows for the profile, returned as ``{media_id: progress}``."""
        if not media_ids:
            return {}
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.profile_id == str(profile_id),
            WatchProgressModel.media_id.in_([media_id.value for media_id in media_ids]),
            WatchProgressModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return {m.media_id: WatchProgressMapper.to_entity(m) for m in result.scalars().all()}

    async def delete(self, media_id: WatchableMediaId, profile_id: ProfileId) -> bool:
        """Soft-delete the row for (profile_id, media_id), if any."""
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.media_id == media_id.value,
            WatchProgressModel.profile_id == str(profile_id),
            WatchProgressModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        model.soft_delete()
        await self._session.flush()
        return True

    async def delete_by_series(
        self,
        series_id: SeriesId,
        profile_id: ProfileId,
    ) -> int:
        """Soft-delete every episode-progress row for this series in the profile."""
        prefix = EpisodeCompositeId.media_id_prefix_for(series_id)
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.profile_id == str(profile_id),
            WatchProgressModel.media_id.startswith(prefix),
            WatchProgressModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            model.soft_delete()
        if models:
            await self._session.flush()
        return len(models)

    async def delete_all_for_profiles(self, profile_ids: list[str]) -> int:
        """Soft-delete every progress row owned by the given profiles.

        Driven by ``UserDeletedEvent`` — see the interface docstring
        for the rationale.
        """
        if not profile_ids:
            return 0
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.profile_id.in_(profile_ids),
            WatchProgressModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            model.soft_delete()
        if models:
            await self._session.flush()
        return len(models)

    async def delete_all_for_movie(self, movie_id: MovieId) -> int:
        """Soft-delete every (cross-profile) progress row on a movie id.

        Driven by ``MoviePromotedToSeriesEvent`` — see the interface
        docstring for the rationale (movie ids vanish on promotion,
        and mapping a half-watched position to a re-cut episode is
        almost guaranteed to be wrong).
        """
        stmt = select(WatchProgressModel).where(
            WatchProgressModel.media_id == movie_id.value,
            WatchProgressModel.media_type == "movie",
            WatchProgressModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            model.soft_delete()
        if models:
            await self._session.flush()
        return len(models)


__all__ = ["SQLAlchemyWatchProgressRepository"]
