"""Scheduler service for recurring library scans.

Wraps APScheduler with a domain-aware reconciliation loop.  The
``Library`` entity stores its own cron expression; this service reads
those rows periodically and mirrors them into the APScheduler job
registry — adding new jobs, removing deleted ones, and replacing jobs
whose cron changed.  Each scan opens its own Unit of Work so
background work never shares a request-scoped session.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config.logging import get_logger
from src.modules.library.domain.value_objects.library_id import LibraryId
from src.modules.media.application.dtos.scan_dtos import ScanMediaInput
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)

if TYPE_CHECKING:
    from src.building_blocks.application.event_bus import EventBus
    from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory
    from src.modules.media.application.ports import (
        FileSystemScanner,
        MediaProbePort,
        VariantDetectorPort,
    )
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory

_logger = get_logger()

_RECONCILE_JOB_ID = "homeflix:reconcile-libraries"
_LIBRARY_JOB_PREFIX = "library-scan:"


def _job_id_for(library_id: str) -> str:
    return f"{_LIBRARY_JOB_PREFIX}{library_id}"


class LibraryScanScheduler:
    """Coordinate cron-driven library scans.

    Single source of truth for schedules is the ``Library`` table; this
    service does not maintain its own job database.  Reconciliation
    runs at startup and on a configurable interval so schedule edits
    made through the REST API propagate without a restart.
    """

    def __init__(
        self,
        library_uow_factory: LibraryUnitOfWorkFactory,
        media_uow_factory: MediaUnitOfWorkFactory,
        file_scanner: FileSystemScanner,
        variant_detector: VariantDetectorPort,
        event_bus: EventBus,
        reconcile_interval_minutes: int,
        probe_service: MediaProbePort | None = None,
    ) -> None:
        self._library_uow_factory = library_uow_factory
        self._media_uow_factory = media_uow_factory
        self._file_scanner = file_scanner
        self._variant_detector = variant_detector
        self._event_bus = event_bus
        self._reconcile_interval_minutes = reconcile_interval_minutes
        self._probe_service = probe_service
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    async def start(self) -> None:
        """Start the scheduler and register the reconcile + initial jobs."""
        self._scheduler.start()
        self._scheduler.add_job(
            self._reconcile,
            trigger="interval",
            minutes=self._reconcile_interval_minutes,
            id=_RECONCILE_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        await self._reconcile()
        _logger.info(
            "[scheduler] Started",
            reconcile_interval_minutes=self._reconcile_interval_minutes,
        )

    async def stop(self) -> None:
        """Shut the scheduler down, waiting for any in-flight jobs."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            _logger.info("[scheduler] Stopped")

    async def _reconcile(self) -> None:
        """Sync APScheduler jobs with the current ``Library`` rows.

        Adds a cron job for each library with a non-empty, valid
        ``scan_schedule``; replaces an existing job whose cron changed;
        removes jobs for libraries that vanished or lost their schedule.
        Invalid crons are logged and skipped — we never crash startup
        or reconciliation over a bad expression.
        """
        async with self._library_uow_factory() as uow:
            libraries = await uow.libraries.find_all()

        desired: dict[str, tuple[str, str]] = {}  # job_id -> (library_id, cron)
        for library in libraries:
            if not library.scan_schedule or library.id is None:
                continue
            library_id = str(library.id)
            desired[_job_id_for(library_id)] = (library_id, library.scan_schedule)

        existing = {
            job.id for job in self._scheduler.get_jobs() if job.id.startswith(_LIBRARY_JOB_PREFIX)
        }

        # Remove jobs no longer desired.
        for job_id in existing - desired.keys():
            self._scheduler.remove_job(job_id)
            _logger.info("[scheduler] Removed job", job_id=job_id)

        # Add or replace desired jobs.
        for job_id, (library_id, cron) in desired.items():
            try:
                trigger = CronTrigger.from_crontab(cron, timezone="UTC")
            except ValueError as exc:
                _logger.warning(
                    "[scheduler] Skipping library: invalid cron",
                    library_id=library_id,
                    cron=cron,
                    error=str(exc),
                )
                if job_id in existing:
                    self._scheduler.remove_job(job_id)
                continue

            self._scheduler.add_job(
                self._run_scan,
                trigger=trigger,
                args=[library_id],
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            _logger.info(
                "[scheduler] Scheduled library",
                library_id=library_id,
                cron=cron,
            )

    async def _run_scan(self, library_id: str) -> None:
        """Run a single library scan and record completion.

        Loads the library in a short-lived UoW, releases it before the
        long-running scan, then opens a fresh UoW to persist
        ``last_scan_at`` on success. The scan use case drives its own
        media UoW per file group so failures on one group roll back
        only that transaction.
        """
        _logger.info("[scheduler] Running scan", library_id=library_id)

        paths = await self._load_library_paths(library_id)
        if paths is None:
            return

        use_case = ScanMediaDirectoriesUseCase(
            file_scanner=self._file_scanner,
            variant_detector=self._variant_detector,
            uow_factory=self._media_uow_factory,
            probe_service=self._probe_service,
            event_bus=self._event_bus,
        )
        try:
            result = await use_case.execute(ScanMediaInput(directories=paths))
        except Exception as exc:
            _logger.error(
                "[scheduler] Scan failed",
                library_id=library_id,
                error=str(exc),
                exc_info=True,
            )
            return

        await self._mark_library_scanned(library_id)

        _logger.info(
            "[scheduler] Scan done",
            library_id=library_id,
            movies_created=result.movies_created,
            movies_updated=result.movies_updated,
            episodes_created=result.episodes_created,
            episodes_updated=result.episodes_updated,
            errors=len(result.errors),
        )

    async def _load_library_paths(self, library_id: str) -> list[str] | None:
        """Return the library's configured paths, or ``None`` if it vanished."""
        async with self._library_uow_factory() as uow:
            library = await uow.libraries.find_by_id(LibraryId(library_id))
            if library is None:
                _logger.warning(
                    "[scheduler] Library vanished before scan; skipping",
                    library_id=library_id,
                )
                return None
            return [p.value for p in library.paths]

    async def _mark_library_scanned(self, library_id: str) -> None:
        """Persist the completed-scan timestamp in its own UoW."""
        async with self._library_uow_factory() as uow:
            library = await uow.libraries.find_by_id(LibraryId(library_id))
            if library is None:
                # Matches the warning emitted at load-time so ops can
                # correlate "scan started" with "scan finished but row
                # vanished" in the logs.
                _logger.warning(
                    "[scheduler] Library vanished before persisting last_scan_at",
                    library_id=library_id,
                )
                return
            updated = library.with_scan_completed(datetime.now(UTC))
            await uow.libraries.save(updated)


__all__ = ["LibraryScanScheduler"]
