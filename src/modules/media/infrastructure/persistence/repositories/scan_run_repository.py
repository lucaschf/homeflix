"""SQLAlchemy implementation of ``ScanRunRepository``."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunStatus,
    ScanRunTrigger,
)
from src.modules.media.domain.repositories.scan_run_repository import ScanRunRepository
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId
from src.modules.media.infrastructure.persistence.mappers.scan_run_mapper import (
    ScanRunMapper,
)
from src.modules.media.infrastructure.persistence.models.scan_run import ScanRunModel


class SqlAlchemyScanRunRepository(ScanRunRepository):
    """Async SQLAlchemy repository for the ``ScanRun`` aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, run: ScanRun) -> ScanRun:
        """Insert when id-less, update when known."""
        run = run.with_updates(id=ScanRunId.generate_if_absent(run.id))

        stmt = select(ScanRunModel).where(ScanRunModel.external_id == str(run.id))
        existing = (await self._session.execute(stmt)).scalar_one_or_none()

        if existing is not None:
            ScanRunMapper.update_model(existing, run)
            await self._session.flush()
        else:
            model = ScanRunMapper.to_model(run)
            self._session.add(model)
            await self._session.flush()

        if run.id is None:  # pragma: no cover — generate_if_absent assigns one
            raise RuntimeError("ScanRun id was not assigned before save")
        saved = await self.find_by_id(run.id)
        if saved is None:  # pragma: no cover — row was just written
            raise RuntimeError(f"ScanRun {run.id} disappeared between flush and reload")
        return saved

    async def find_by_id(self, run_id: ScanRunId) -> ScanRun | None:
        """Look up a non-deleted run by external id."""
        stmt = select(ScanRunModel).where(
            ScanRunModel.external_id == str(run_id),
            ScanRunModel.deleted_at.is_(None),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else ScanRunMapper.to_entity(model)

    async def list_paginated(
        self,
        *,
        kind: ScanRunKind | None = None,
        trigger: ScanRunTrigger | None = None,
        library_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ScanRun]:
        """List non-deleted runs newest-first with optional filters."""
        stmt = select(ScanRunModel).where(ScanRunModel.deleted_at.is_(None))
        if kind is not None:
            stmt = stmt.where(ScanRunModel.kind == kind.value)
        if trigger is not None:
            stmt = stmt.where(ScanRunModel.trigger == trigger.value)
        if library_id is not None:
            stmt = stmt.where(ScanRunModel.library_id == library_id)
        stmt = stmt.order_by(ScanRunModel.started_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [ScanRunMapper.to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        *,
        kind: ScanRunKind | None = None,
        trigger: ScanRunTrigger | None = None,
        library_id: str | None = None,
    ) -> int:
        """Count non-deleted runs matching the filter."""
        stmt = select(func.count(ScanRunModel.id)).where(ScanRunModel.deleted_at.is_(None))
        if kind is not None:
            stmt = stmt.where(ScanRunModel.kind == kind.value)
        if trigger is not None:
            stmt = stmt.where(ScanRunModel.trigger == trigger.value)
        if library_id is not None:
            stmt = stmt.where(ScanRunModel.library_id == library_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_by_status(self, status: ScanRunStatus) -> Sequence[ScanRun]:
        """List non-deleted runs in a given status."""
        stmt = (
            select(ScanRunModel)
            .where(
                ScanRunModel.deleted_at.is_(None),
                ScanRunModel.status == status.value,
            )
            .order_by(ScanRunModel.started_at.desc())
        )
        result = await self._session.execute(stmt)
        return [ScanRunMapper.to_entity(m) for m in result.scalars().all()]


__all__ = ["SqlAlchemyScanRunRepository"]
