"""Orchestrator that wraps a scan / bulk-enrich execution with run-row bookkeeping.

The "run a scan" flow always boils down to three steps: open a
``running`` row, do the work, write the terminal state. Wrapping it
once in this service keeps the trigger use cases (HTTP-facing) and
the scheduler (background job) on the same path — both end up
calling :meth:`run_scan` / :meth:`run_bulk_enrich`. The HTTP route
spawns the call via :func:`asyncio.create_task` for fire-and-forget;
the scheduler awaits it directly inside its existing job loop.

Failures inside the work raise; the service catches them so the
row can transition to ``failed`` with the message in ``errors``,
then re-raises (or in fire-and-forget mode, just logs). On
process restart any rows still marked ``running`` get swept to
``interrupted`` by the lifespan startup hook (see
:class:`SweepInterruptedScanRunsUseCase`).
"""

import logging

from src.modules.library.domain.entities.library import Library
from src.modules.media.application.dtos.enrichment_dtos import BulkEnrichInput
from src.modules.media.application.dtos.scan_dtos import ScanMediaInput
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases.bulk_enrich_metadata import (
    BulkEnrichMetadataUseCase,
)
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunTrigger,
)
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId

_logger = logging.getLogger(__name__)


class ScanRunService:
    """Wraps scan + bulk-enrich execution with run-row lifecycle writes.

    Single instance held in the DI container — the underlying use
    cases + UoW factory are reused across every run. The service
    itself holds no per-run state; the durable record lives in
    ``scan_runs``.
    """

    def __init__(
        self,
        scan_use_case: ScanMediaDirectoriesUseCase,
        bulk_enrich_use_case: BulkEnrichMetadataUseCase,
        media_uow_factory: MediaUnitOfWorkFactory,
    ) -> None:
        self._scan = scan_use_case
        self._bulk_enrich = bulk_enrich_use_case
        self._media_uow_factory = media_uow_factory

    async def open_scan(
        self,
        library_id: str,
        trigger: ScanRunTrigger,
    ) -> ScanRun:
        """Write the ``running`` row for a scan; return the saved aggregate."""
        async with self._media_uow_factory() as uow:
            return await uow.scan_runs.save(
                ScanRun.start(
                    kind=ScanRunKind.SCAN,
                    trigger=trigger,
                    library_id=library_id,
                ),
            )

    async def open_bulk_enrich(self, trigger: ScanRunTrigger) -> ScanRun:
        """Write the ``running`` row for a bulk enrich; return the aggregate."""
        async with self._media_uow_factory() as uow:
            return await uow.scan_runs.save(
                ScanRun.start(
                    kind=ScanRunKind.ENRICH,
                    trigger=trigger,
                    library_id=None,
                ),
            )

    async def run_scan(self, run_id: ScanRunId, library: Library) -> None:
        """Execute the scan and write the terminal row.

        Args:
            run_id: External id of the already-opened ``running`` row.
            library: Pre-loaded library so the runner doesn't re-hit
                the library UoW from inside the background task.
        """
        try:
            output = await self._scan.execute(
                ScanMediaInput(
                    library_id=str(library.id),
                    directories=list(library.paths),
                ),
            )
            summary = {
                "movies_created": output.movies_created,
                "movies_updated": output.movies_updated,
                "episodes_created": output.episodes_created,
                "episodes_updated": output.episodes_updated,
            }
            await self._finalize_succeeded(run_id, summary, output.errors)
        except Exception as exc:
            _logger.exception("Scan run %s crashed for library %s", run_id, library.id)
            await self._finalize_failed(run_id, str(exc))

    async def run_bulk_enrich(self, run_id: ScanRunId, force: bool) -> None:
        """Execute the bulk enrich and write the terminal row."""
        try:
            output = await self._bulk_enrich.execute(BulkEnrichInput(force=force))
            summary = {
                "movies_enriched": output.movies_enriched,
                "series_enriched": output.series_enriched,
                "skipped": output.skipped,
            }
            await self._finalize_succeeded(run_id, summary, output.errors)
        except Exception as exc:
            _logger.exception("Bulk enrich run %s crashed", run_id)
            await self._finalize_failed(run_id, str(exc))

    async def _finalize_succeeded(
        self,
        run_id: ScanRunId,
        summary: dict[str, int],
        errors: list[str],
    ) -> None:
        async with self._media_uow_factory() as uow:
            run = await uow.scan_runs.find_by_id(run_id)
            if run is None:  # pragma: no cover — defensive, deleted mid-run
                _logger.warning("scan_run %s disappeared before finalize", run_id)
                return
            await uow.scan_runs.save(run.succeed(summary, errors))

    async def _finalize_failed(self, run_id: ScanRunId, error_message: str) -> None:
        async with self._media_uow_factory() as uow:
            run = await uow.scan_runs.find_by_id(run_id)
            if run is None:  # pragma: no cover
                _logger.warning("scan_run %s disappeared before failure", run_id)
                return
            await uow.scan_runs.save(run.fail(error_message))


__all__ = ["ScanRunService"]
