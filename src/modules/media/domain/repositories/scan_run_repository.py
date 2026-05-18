"""ScanRun repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunStatus,
    ScanRunTrigger,
)
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId


class ScanRunRepository(ABC):
    """Repository for the ``ScanRun`` aggregate.

    Backs the admin scan + bulk-enrich history page. Writes are
    cheap (one row per trigger + one update on completion), reads
    are bounded by ``limit`` so the list page stays paged.
    """

    @abstractmethod
    async def save(self, run: ScanRun) -> ScanRun:
        """Persist a run (insert when ``id`` is fresh, update when known).

        The repository assigns a new :class:`ScanRunId` on insert and
        re-reads the row so callers see server-applied timestamps.
        """
        ...

    @abstractmethod
    async def find_by_id(self, run_id: ScanRunId) -> ScanRun | None:
        """Look up a non-deleted run by its external id."""
        ...

    @abstractmethod
    async def list_paginated(
        self,
        *,
        kind: ScanRunKind | None = None,
        trigger: ScanRunTrigger | None = None,
        library_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ScanRun]:
        """List runs newest-first, optionally narrowed by kind/trigger/library.

        Args:
            kind: Filter to scans or enriches.
            trigger: Filter to manual or scheduled runs.
            library_id: Filter to a single library's runs (useful
                when the operator clicks a library detail and wants
                to see only its history).
            limit: Page size cap.
            offset: Rows to skip from the head of the result.

        Returns:
            Runs ordered by ``started_at`` descending.
        """
        ...

    @abstractmethod
    async def count(
        self,
        *,
        kind: ScanRunKind | None = None,
        trigger: ScanRunTrigger | None = None,
        library_id: str | None = None,
    ) -> int:
        """Count matching non-deleted runs."""
        ...

    @abstractmethod
    async def list_by_status(self, status: ScanRunStatus) -> Sequence[ScanRun]:
        """List every run in a given status (no pagination).

        Used by the lifespan startup hook to sweep rows that were
        ``running`` when the process died.
        """
        ...


__all__ = ["ScanRunRepository"]
