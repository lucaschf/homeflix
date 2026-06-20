"""JobRun aggregate — one recorded execution of a scheduler job."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Self

from pydantic import Field

from src.building_blocks.domain import AggregateRoot
from src.modules.media.domain.value_objects.job_run_id import JobRunId

_MAX_ERROR_LEN = 2000


class JobRunStatus(str, Enum):
    """Lifecycle state of a recorded job execution."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class JobRun(AggregateRoot[JobRunId]):
    """A single execution of a background scheduler job.

    Generic execution log shared by every recurring job (thumbnail
    backfill, intro/credits detection, scheduled scans, dedup sweep).
    Each tick writes a ``running`` row up front and transitions to a
    terminal state when the work finishes, so the admin Jobs page can
    show "last run / outcome / duration" and "running now" uniformly —
    even for jobs that keep no domain-specific history of their own.

    Attributes:
        id: External id (``job_xxx``).
        job_id: Stable scheduler job identifier (e.g.
            ``homeflix:thumbnail-backfill`` or ``library-scan:lib_x``).
        status: Current lifecycle state.
        started_at: When the tick began.
        finished_at: ``None`` while ``running``; set on terminal states.
        error: Failure message when ``status == failed`` (truncated),
            else ``None``.
    """

    id: JobRunId | None = Field(default=None)

    job_id: str
    status: JobRunStatus = JobRunStatus.RUNNING
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    error: str | None = None

    @classmethod
    def start(cls, job_id: str) -> Self:
        """Open a new run row in the ``running`` state."""
        return cls(
            job_id=job_id,
            status=JobRunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

    def succeed(self) -> Self:
        """Return a copy stamped ``succeeded`` with a finish timestamp."""
        return self.with_updates(
            status=JobRunStatus.SUCCEEDED,
            finished_at=datetime.now(UTC),
            error=None,
        )

    def fail(self, error_message: str) -> Self:
        """Return a copy stamped ``failed`` with the truncated error."""
        return self.with_updates(
            status=JobRunStatus.FAILED,
            finished_at=datetime.now(UTC),
            error=error_message[:_MAX_ERROR_LEN],
        )

    def mark_interrupted(self) -> Self:
        """Mark a ``running`` row as interrupted by a process restart."""
        return self.with_updates(
            status=JobRunStatus.INTERRUPTED,
            finished_at=datetime.now(UTC),
            error="Process restarted while the job was in progress.",
        )

    @property
    def duration_ms(self) -> int | None:
        """Elapsed milliseconds, or ``None`` while still running."""
        if self.finished_at is None:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


__all__ = ["JobRun", "JobRunStatus"]
