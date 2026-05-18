"""ScanRun aggregate — admin scan + bulk-enrich history row."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Self

from pydantic import Field

from src.building_blocks.domain import AggregateRoot
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId


class ScanRunKind(str, Enum):
    """What was being run."""

    SCAN = "scan"
    ENRICH = "enrich"


class ScanRunTrigger(str, Enum):
    """Who started the run."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"


class ScanRunStatus(str, Enum):
    """Lifecycle state of a run."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


_MAX_ERRORS_RETAINED = 50


class ScanRun(AggregateRoot[ScanRunId]):
    """A single execution of a catalog scan or bulk metadata enrich.

    History row for the admin panel: every run (manual or
    scheduled) writes a ``running`` row up front, then transitions
    to a terminal state when the async work finishes. Counters are
    kept per-kind in the ``summary`` dict to avoid a wide table
    with mostly-null columns.

    Why not split into two tables: the admin history page renders
    a unified timeline and both kinds share the same
    ``running → succeeded/failed/interrupted`` lifecycle. One table
    keeps the page query simple and the operator's mental model
    coherent ("here's what happened to the catalog recently").

    Attributes:
        id: External id (``run_xxx``).
        kind: Scan or enrich.
        trigger: Manual (admin button) or scheduled (background
            poller). Filterable on the list page so the operator
            can ignore cron noise.
        library_id: External id of the targeted library. ``None``
            for enrich runs that aren't library-scoped.
        started_at: When the runner began work.
        finished_at: ``None`` while ``running``; set on terminal
            transitions.
        status: Current lifecycle state.
        summary: Per-kind counter dict. For scans:
            ``movies_created`` / ``movies_updated`` /
            ``episodes_created`` / ``episodes_updated``.
            For enrich: ``enriched`` / ``skipped`` / ``failed``.
        errors: First N error messages emitted during the run.
            Truncated to ``_MAX_ERRORS_RETAINED`` so a degenerate
            scan can't bloat the row.
    """

    id: ScanRunId | None = Field(default=None)

    kind: ScanRunKind
    trigger: ScanRunTrigger
    library_id: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    status: ScanRunStatus = ScanRunStatus.RUNNING
    summary: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    @classmethod
    def start(
        cls,
        *,
        kind: ScanRunKind,
        trigger: ScanRunTrigger,
        library_id: str | None,
    ) -> Self:
        """Open a new run row in the ``running`` state."""
        return cls(
            kind=kind,
            trigger=trigger,
            library_id=library_id,
            started_at=datetime.now(UTC),
            status=ScanRunStatus.RUNNING,
        )

    def succeed(self, summary: dict[str, Any], errors: list[str]) -> Self:
        """Return a copy stamped with ``succeeded`` + the final counters."""
        return self.with_updates(
            status=ScanRunStatus.SUCCEEDED,
            finished_at=datetime.now(UTC),
            summary=summary,
            errors=list(errors[:_MAX_ERRORS_RETAINED]),
        )

    def fail(self, error_message: str, summary: dict[str, Any] | None = None) -> Self:
        """Return a copy stamped with ``failed`` + the error message.

        Used when the runner itself raised (vs. completing with a
        bag of per-file errors). ``summary`` may carry partial
        counters if some work succeeded before the crash.
        """
        return self.with_updates(
            status=ScanRunStatus.FAILED,
            finished_at=datetime.now(UTC),
            summary=summary or self.summary,
            errors=[error_message],
        )

    def mark_interrupted(self) -> Self:
        """Mark a ``running`` row as interrupted by a process restart."""
        return self.with_updates(
            status=ScanRunStatus.INTERRUPTED,
            finished_at=datetime.now(UTC),
            errors=["Process restarted while the run was in progress."],
        )


__all__ = [
    "ScanRun",
    "ScanRunKind",
    "ScanRunStatus",
    "ScanRunTrigger",
]
