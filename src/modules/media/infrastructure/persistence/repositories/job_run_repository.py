"""SQLAlchemy implementation of ``JobRunRepository``."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities.job_run import JobRun, JobRunStatus
from src.modules.media.domain.repositories.job_run_repository import JobRunRepository
from src.modules.media.domain.value_objects.job_run_id import JobRunId
from src.modules.media.infrastructure.persistence.mappers.job_run_mapper import JobRunMapper
from src.modules.media.infrastructure.persistence.models.job_run import JobRunModel


class SqlAlchemyJobRunRepository(JobRunRepository):
    """Async SQLAlchemy repository for the ``JobRun`` log."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, run: JobRun) -> JobRun:
        """Insert when id-less, update when known."""
        run = run.with_updates(id=JobRunId.generate_if_absent(run.id))

        stmt = select(JobRunModel).where(JobRunModel.external_id == str(run.id))
        existing = (await self._session.execute(stmt)).scalar_one_or_none()

        if existing is not None:
            JobRunMapper.update_model(existing, run)
        else:
            self._session.add(JobRunMapper.to_model(run))
        await self._session.flush()

        if run.id is None:  # pragma: no cover — generate_if_absent assigns one
            raise RuntimeError("JobRun id was not assigned before save")
        saved = await self.find_by_id(run.id)
        if saved is None:  # pragma: no cover — row was just written
            raise RuntimeError(f"JobRun {run.id} disappeared between flush and reload")
        return saved

    async def find_by_id(self, run_id: JobRunId) -> JobRun | None:
        """Look up a non-deleted run by external id."""
        stmt = select(JobRunModel).where(
            JobRunModel.external_id == str(run_id),
            JobRunModel.deleted_at.is_(None),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else JobRunMapper.to_entity(model)

    async def list_paginated(
        self,
        *,
        job_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[JobRun]:
        """List non-deleted runs newest-first, optionally for one job."""
        stmt = select(JobRunModel).where(JobRunModel.deleted_at.is_(None))
        if job_id is not None:
            stmt = stmt.where(JobRunModel.job_id == job_id)
        stmt = stmt.order_by(JobRunModel.started_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [JobRunMapper.to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        *,
        job_id: str | None = None,
        since: datetime | None = None,
        statuses: Sequence[JobRunStatus] | None = None,
    ) -> int:
        """Count non-deleted runs matching the filters."""
        stmt = select(func.count(JobRunModel.id)).where(JobRunModel.deleted_at.is_(None))
        if job_id is not None:
            stmt = stmt.where(JobRunModel.job_id == job_id)
        if since is not None:
            stmt = stmt.where(JobRunModel.started_at >= since)
        if statuses is not None:
            stmt = stmt.where(JobRunModel.status.in_([s.value for s in statuses]))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def latest_per_job(self) -> Sequence[JobRun]:
        """Return the newest non-deleted run per distinct ``job_id``."""
        row_number = (
            func.row_number()
            .over(
                partition_by=JobRunModel.job_id,
                order_by=(JobRunModel.started_at.desc(), JobRunModel.id.desc()),
            )
            .label("rn")
        )
        ranked = (
            select(JobRunModel.id, row_number).where(JobRunModel.deleted_at.is_(None)).subquery()
        )
        stmt = (
            select(JobRunModel)
            .join(ranked, JobRunModel.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(JobRunModel.job_id.asc())
        )
        result = await self._session.execute(stmt)
        return [JobRunMapper.to_entity(m) for m in result.scalars().all()]

    async def recent_per_job(self, *, limit: int) -> Sequence[JobRun]:
        """Return up to ``limit`` newest non-deleted runs per distinct job."""
        row_number = (
            func.row_number()
            .over(
                partition_by=JobRunModel.job_id,
                order_by=(JobRunModel.started_at.desc(), JobRunModel.id.desc()),
            )
            .label("rn")
        )
        ranked = (
            select(JobRunModel.id, row_number).where(JobRunModel.deleted_at.is_(None)).subquery()
        )
        stmt = (
            select(JobRunModel)
            .join(ranked, JobRunModel.id == ranked.c.id)
            .where(ranked.c.rn <= limit)
            .order_by(
                JobRunModel.job_id.asc(),
                JobRunModel.started_at.desc(),
                JobRunModel.id.desc(),
            )
        )
        result = await self._session.execute(stmt)
        return [JobRunMapper.to_entity(m) for m in result.scalars().all()]

    async def list_by_status(self, status: JobRunStatus) -> Sequence[JobRun]:
        """List non-deleted runs in a given status."""
        stmt = (
            select(JobRunModel)
            .where(
                JobRunModel.deleted_at.is_(None),
                JobRunModel.status == status.value,
            )
            .order_by(JobRunModel.started_at.desc())
        )
        result = await self._session.execute(stmt)
        return [JobRunMapper.to_entity(m) for m in result.scalars().all()]

    async def prune(self, job_id: str, *, keep: int) -> int:
        """Soft-delete all but the newest ``keep`` runs of ``job_id``."""
        stale = (
            select(JobRunModel.id)
            .where(
                JobRunModel.job_id == job_id,
                JobRunModel.deleted_at.is_(None),
            )
            .order_by(JobRunModel.started_at.desc(), JobRunModel.id.desc())
            .offset(keep)
        )
        result = await self._session.execute(
            update(JobRunModel)
            .where(JobRunModel.id.in_(stale.scalar_subquery()))
            .values(deleted_at=datetime.now(UTC)),
        )
        await self._session.flush()
        return int(result.rowcount or 0)


__all__ = ["SqlAlchemyJobRunRepository"]
