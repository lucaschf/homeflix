"""SweepInterruptedJobRunsUseCase — startup repair for orphan ``running`` rows."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.modules.media.domain.entities.job_run import JobRunStatus

if TYPE_CHECKING:
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory

_logger = logging.getLogger(__name__)


class SweepInterruptedJobRunsUseCase:
    """Mark every ``running`` ``job_runs`` row as ``interrupted``.

    Runs once during ``lifespan`` startup. A job tick that was in
    flight when the process died would otherwise leave a row stuck in
    ``running``, making the dashboard show a job as perpetually active.
    """

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def execute(self) -> int:
        """Sweep + return the number of rows transitioned."""
        async with self._media_uow_factory() as uow:
            running = await uow.job_runs.list_by_status(JobRunStatus.RUNNING)
            for run in running:
                await uow.job_runs.save(run.mark_interrupted())

        if running:
            _logger.warning(
                "Marked %d orphan job_runs as 'interrupted' on startup.",
                len(running),
            )
        return len(running)


__all__ = ["SweepInterruptedJobRunsUseCase"]
