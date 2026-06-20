"""Records scheduler-job executions to the ``job_runs`` log.

A single seam the scheduler wraps every recurring job with: open a
``running`` row, run the work, write the terminal state. This gives the
admin Jobs dashboard a uniform "last run / outcome / duration / running
now" view even for jobs (backfill, dedup) that keep no history of their
own. Failures are caught, recorded as ``failed`` and swallowed — a job
that raises must not take down the scheduler tick (APScheduler would
only log it otherwise), and the row makes the failure visible.

On process restart any rows still ``running`` are swept to
``interrupted`` by the lifespan startup hook (see
:class:`SweepInterruptedJobRunsUseCase`).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.modules.media.domain.entities.job_run import JobRun

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.value_objects.job_run_id import JobRunId

_logger = logging.getLogger(__name__)

# Bound the per-job history so high-frequency jobs (e.g. backfill every
# 20 min) can't grow the table without limit. Older rows are soft-deleted
# after each finished run.
_HISTORY_RETAINED_PER_JOB = 100


class JobRunService:
    """Wrap a job's execution with ``job_runs`` lifecycle bookkeeping."""

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def record(self, job_id: str, func: Callable[[], Awaitable[None]]) -> None:
        """Run ``func`` while recording a ``job_runs`` row for ``job_id``."""
        run_id = await self._open(job_id)
        try:
            await func()
        except Exception as exc:  # must not break the scheduler tick
            _logger.exception("Job %s crashed", job_id)
            message = str(exc)
            await self._finalize(run_id, lambda run: run.fail(message))
        else:
            await self._finalize(run_id, lambda run: run.succeed())
        await self._prune(job_id)

    async def _open(self, job_id: str) -> JobRunId:
        async with self._media_uow_factory() as uow:
            saved = await uow.job_runs.save(JobRun.start(job_id))
        if saved.id is None:  # pragma: no cover — repo always assigns
            raise RuntimeError("JobRun id was not assigned on open")
        return saved.id

    async def _finalize(
        self,
        run_id: JobRunId,
        transition: Callable[[JobRun], JobRun],
    ) -> None:
        async with self._media_uow_factory() as uow:
            run = await uow.job_runs.find_by_id(run_id)
            if run is None:  # pragma: no cover — defensive, deleted mid-run
                _logger.warning("job_run %s disappeared before finalize", run_id)
                return
            await uow.job_runs.save(transition(run))

    async def _prune(self, job_id: str) -> None:
        async with self._media_uow_factory() as uow:
            await uow.job_runs.prune(job_id, keep=_HISTORY_RETAINED_PER_JOB)


__all__ = ["JobRunService"]
