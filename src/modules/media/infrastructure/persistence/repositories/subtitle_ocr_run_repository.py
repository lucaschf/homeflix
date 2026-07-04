"""SQLAlchemy implementation of SubtitleOcrRunRepository."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities.subtitle_ocr_run import SubtitleOcrRun
from src.modules.media.domain.repositories.subtitle_ocr_run_repository import (
    SubtitleOcrRunRepository,
)
from src.modules.media.domain.value_objects.subtitle_ocr_run_id import SubtitleOcrRunId
from src.modules.media.infrastructure.persistence.mappers.subtitle_ocr_run_mapper import (
    SubtitleOcrRunMapper,
)
from src.modules.media.infrastructure.persistence.models.subtitle_ocr_run import (
    SubtitleOcrRunModel,
)


class SqlAlchemySubtitleOcrRunRepository(SubtitleOcrRunRepository):
    """Append-only store backed by the ``subtitle_ocr_runs`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run: SubtitleOcrRun) -> SubtitleOcrRun:
        """Insert a new run with a fresh id, then re-read it."""
        run_id = SubtitleOcrRunId.generate_if_absent(run.id)
        self._session.add(SubtitleOcrRunMapper.to_model(run.with_updates(id=run_id)))
        await self._session.flush()
        saved = await self.find_by_id(run_id)
        if saved is None:
            raise RuntimeError(f"SubtitleOcrRun {run_id} disappeared after insert")
        return saved

    async def find_by_id(self, run_id: SubtitleOcrRunId) -> SubtitleOcrRun | None:
        """Look up a non-deleted run by external id."""
        stmt = select(SubtitleOcrRunModel).where(
            SubtitleOcrRunModel.external_id == str(run_id),
            SubtitleOcrRunModel.deleted_at.is_(None),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else SubtitleOcrRunMapper.to_entity(model)

    async def list_paginated(
        self,
        *,
        media_kind: str | None = None,
        media_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[SubtitleOcrRun]:
        """List non-deleted runs newest-first with optional filters."""
        stmt = select(SubtitleOcrRunModel).where(SubtitleOcrRunModel.deleted_at.is_(None))
        if media_kind is not None:
            stmt = stmt.where(SubtitleOcrRunModel.media_kind == media_kind)
        if media_id is not None:
            stmt = stmt.where(SubtitleOcrRunModel.media_id == media_id)
        stmt = stmt.order_by(SubtitleOcrRunModel.started_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [SubtitleOcrRunMapper.to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        *,
        media_kind: str | None = None,
        media_id: str | None = None,
    ) -> int:
        """Count non-deleted runs matching the filter."""
        stmt = select(func.count(SubtitleOcrRunModel.id)).where(
            SubtitleOcrRunModel.deleted_at.is_(None)
        )
        if media_kind is not None:
            stmt = stmt.where(SubtitleOcrRunModel.media_kind == media_kind)
        if media_id is not None:
            stmt = stmt.where(SubtitleOcrRunModel.media_id == media_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())


__all__ = ["SqlAlchemySubtitleOcrRunRepository"]
