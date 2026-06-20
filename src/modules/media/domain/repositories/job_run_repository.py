"""JobRun repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.media.domain.entities.job_run import JobRun, JobRunStatus
from src.modules.media.domain.value_objects.job_run_id import JobRunId


class JobRunRepository(ABC):
    """Repository for the ``JobRun`` execution log.

    Backs the admin Jobs dashboard. Writes are cheap (one insert +
    one update per tick); reads are bounded by ``limit`` for the
    history list and by job for the "last run per job" summary.
    """

    @abstractmethod
    async def save(self, run: JobRun) -> JobRun:
        """Insert when id-less, update when known; re-read and return it."""
        ...

    @abstractmethod
    async def find_by_id(self, run_id: JobRunId) -> JobRun | None:
        """Look up a non-deleted run by external id."""
        ...

    @abstractmethod
    async def list_paginated(
        self,
        *,
        job_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[JobRun]:
        """List runs newest-first, optionally narrowed to one ``job_id``."""
        ...

    @abstractmethod
    async def count(self, *, job_id: str | None = None) -> int:
        """Count matching non-deleted runs."""
        ...

    @abstractmethod
    async def latest_per_job(self) -> Sequence[JobRun]:
        """Return the most recent run for each distinct ``job_id``.

        Powers the dashboard's per-job "last run / status / duration"
        column without loading the full history.
        """
        ...

    @abstractmethod
    async def list_by_status(self, status: JobRunStatus) -> Sequence[JobRun]:
        """List every run in a given status (used by the startup sweep)."""
        ...

    @abstractmethod
    async def prune(self, job_id: str, *, keep: int) -> int:
        """Soft-delete all but the newest ``keep`` runs of ``job_id``.

        Keeps the append-only log bounded for high-frequency jobs.
        Returns the number of rows pruned.
        """
        ...


__all__ = ["JobRunRepository"]
