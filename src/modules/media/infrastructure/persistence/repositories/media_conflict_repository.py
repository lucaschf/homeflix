"""SQLAlchemy implementation of ``MediaConflictRepository``."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.building_blocks.application.pagination import (
    PaginatedResult,
    Pagination,
    decode_cursor,
    encode_cursor,
)
from src.modules.media.domain.entities.media_conflict import (
    MediaConflict,
    ResolutionAction,
)
from src.modules.media.domain.repositories.media_conflict_repository import (
    MediaConflictRepository,
)
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId
from src.modules.media.infrastructure.persistence.mappers.media_conflict_mapper import (
    MediaConflictMapper,
)
from src.modules.media.infrastructure.persistence.models.media_conflict import (
    MediaConflictModel,
)


class SqlAlchemyMediaConflictRepository(MediaConflictRepository):
    """Async SQLAlchemy repository for the ``MediaConflict`` aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, conflict: MediaConflict) -> MediaConflict:
        """Insert when id-less, update when known."""
        conflict = conflict.with_updates(
            id=MediaConflictId.generate_if_absent(conflict.id),
        )

        stmt = select(MediaConflictModel).where(
            MediaConflictModel.external_id == str(conflict.id),
        )
        existing = (await self._session.execute(stmt)).scalar_one_or_none()

        if existing is not None:
            MediaConflictMapper.update_model(existing, conflict)
            await self._session.flush()
        else:
            model = MediaConflictMapper.to_model(conflict)
            self._session.add(model)
            await self._session.flush()

        if conflict.id is None:  # pragma: no cover — generate_if_absent assigns one
            raise RuntimeError("MediaConflict id was not assigned before save")
        saved = await self.find_by_id(conflict.id)
        if saved is None:  # pragma: no cover — row was just written
            raise RuntimeError(f"MediaConflict {conflict.id} disappeared between flush and reload")
        return saved

    async def find_by_id(self, conflict_id: MediaConflictId) -> MediaConflict | None:
        """Look up a non-deleted conflict by external id."""
        stmt = select(MediaConflictModel).where(
            MediaConflictModel.external_id == str(conflict_id),
            MediaConflictModel.deleted_at.is_(None),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else MediaConflictMapper.to_entity(model)

    async def find_blocking_pair(
        self,
        candidate_a_id: str,
        candidate_b_id: str,
    ) -> MediaConflict | None:
        """Return any pending or MARK_DISTINCT row for the unordered pair.

        Newest row wins when multiple candidates exist — typical only
        when the same pair was queued, marked distinct, and then a
        future enrich pass tried to re-queue (which this query
        prevents from succeeding).
        """
        a_b = (MediaConflictModel.candidate_a_id == candidate_a_id) & (
            MediaConflictModel.candidate_b_id == candidate_b_id
        )
        b_a = (MediaConflictModel.candidate_a_id == candidate_b_id) & (
            MediaConflictModel.candidate_b_id == candidate_a_id
        )
        # Block on either pending rows OR MARK_DISTINCT-resolved rows.
        # MERGE-resolved rows are excluded — the loser is soft-deleted
        # by the time we get here, so the detector cannot rediscover
        # the pair.
        stmt = (
            select(MediaConflictModel)
            .where(
                or_(a_b, b_a),
                MediaConflictModel.deleted_at.is_(None),
                or_(
                    MediaConflictModel.resolved_at.is_(None),
                    MediaConflictModel.resolution == ResolutionAction.MARK_DISTINCT.value,
                ),
            )
            .order_by(MediaConflictModel.id.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else MediaConflictMapper.to_entity(model)

    async def list_pending(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> PaginatedResult[MediaConflict]:
        """List pending conflicts newest-first with opaque cursor pagination."""
        stmt = select(MediaConflictModel).where(
            MediaConflictModel.resolved_at.is_(None),
            MediaConflictModel.deleted_at.is_(None),
        )

        decoded = decode_cursor(cursor)
        if decoded is not None:
            stmt = stmt.where(MediaConflictModel.id < decoded.id)

        stmt = stmt.order_by(MediaConflictModel.id.desc()).limit(limit + 1)

        result = await self._session.execute(stmt)
        models = list(result.scalars().all())

        has_more = len(models) > limit
        page_models = models[:limit] if has_more else models
        next_cursor = encode_cursor(page_models[-1].id) if has_more and page_models else None

        return PaginatedResult(
            items=[MediaConflictMapper.to_entity(m) for m in page_models],
            pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
        )


__all__ = ["SqlAlchemyMediaConflictRepository"]
