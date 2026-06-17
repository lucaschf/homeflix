"""SQLAlchemy implementation of IntroDetectionRunRepository."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities.intro_detection_run import IntroDetectionRun
from src.modules.media.domain.repositories.intro_detection_run_repository import (
    IntroDetectionRunRepository,
)
from src.modules.media.domain.value_objects.intro_detection_run_id import IntroDetectionRunId
from src.modules.media.infrastructure.persistence.mappers.intro_detection_run_mapper import (
    IntroDetectionRunMapper,
)
from src.modules.media.infrastructure.persistence.models.intro_detection_run import (
    IntroDetectionRunModel,
)


class SqlAlchemyIntroDetectionRunRepository(IntroDetectionRunRepository):
    """Append-only store backed by the ``intro_detection_runs`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run: IntroDetectionRun) -> IntroDetectionRun:
        """Insert a new run with a fresh id, then re-read it."""
        run_id = IntroDetectionRunId.generate_if_absent(run.id)
        self._session.add(IntroDetectionRunMapper.to_model(run.with_updates(id=run_id)))
        await self._session.flush()
        saved = await self.find_by_id(run_id)
        if saved is None:
            raise RuntimeError(f"IntroDetectionRun {run_id} disappeared after insert")
        return saved

    async def find_by_id(self, run_id: IntroDetectionRunId) -> IntroDetectionRun | None:
        """Look up a non-deleted run by external id."""
        stmt = select(IntroDetectionRunModel).where(
            IntroDetectionRunModel.external_id == str(run_id),
            IntroDetectionRunModel.deleted_at.is_(None),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else IntroDetectionRunMapper.to_entity(model)

    async def list_paginated(
        self,
        *,
        season_id: str | None = None,
        series_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[IntroDetectionRun]:
        """List non-deleted runs newest-first with optional filters."""
        stmt = select(IntroDetectionRunModel).where(IntroDetectionRunModel.deleted_at.is_(None))
        if season_id is not None:
            stmt = stmt.where(IntroDetectionRunModel.season_id == season_id)
        if series_id is not None:
            stmt = stmt.where(IntroDetectionRunModel.series_id == series_id)
        stmt = stmt.order_by(IntroDetectionRunModel.started_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [IntroDetectionRunMapper.to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        *,
        season_id: str | None = None,
        series_id: str | None = None,
    ) -> int:
        """Count non-deleted runs matching the filter."""
        stmt = select(func.count(IntroDetectionRunModel.id)).where(
            IntroDetectionRunModel.deleted_at.is_(None)
        )
        if season_id is not None:
            stmt = stmt.where(IntroDetectionRunModel.season_id == season_id)
        if series_id is not None:
            stmt = stmt.where(IntroDetectionRunModel.series_id == series_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())


__all__ = ["SqlAlchemyIntroDetectionRunRepository"]
