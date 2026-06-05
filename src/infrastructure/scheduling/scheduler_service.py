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
from src.modules.media.domain.entities.scan_run import ScanRunTrigger
from src.shared_kernel.value_objects.library_id import LibraryId

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory
    from src.modules.library.domain.entities.library import Library
    from src.modules.media.application.services.scan_run_service import ScanRunService
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings

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

    The reconcile interval is read from :class:`RuntimeSettings` at
    ``start()`` time so admin-panel edits land on the next deploy
    (changing the APScheduler interval at runtime would require
    rebuilding the registered job and is out of scope for ADR-013
    phase 2 — documented limitation).
    """

    def __init__(
        self,
        library_uow_factory: LibraryUnitOfWorkFactory,
        scan_run_service: ScanRunService,
        runtime_settings: RuntimeSettings,
    ) -> None:
        self._library_uow_factory = library_uow_factory
        self._scan_run_service = scan_run_service
        self._runtime_settings = runtime_settings
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    async def start(self) -> None:
        """Start the scheduler and register the reconcile + initial jobs."""
        config = await self._runtime_settings.scheduler()
        self._scheduler.start()
        self._scheduler.add_job(
            self._reconcile,
            trigger="interval",
            minutes=config.reconcile_interval_minutes,
            id=_RECONCILE_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        await self._reconcile()
        _logger.info(
            "[scheduler] Started",
            reconcile_interval_minutes=config.reconcile_interval_minutes,
        )

    async def stop(self) -> None:
        """Shut the scheduler down, waiting for any in-flight jobs."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            _logger.info("[scheduler] Stopped")

    def add_interval_job(
        self,
        func: Callable[[], Awaitable[None]],
        minutes: int,
        job_id: str,
    ) -> None:
        """Register an extra recurring async job alongside library scans.

        Lets infrastructure-level routines (thumbnail backfill today;
        future periodic enrichment) share this scheduler instead of
        each spinning up their own ``AsyncIOScheduler``. Always uses
        ``max_instances=1`` and ``coalesce=True`` so a slow tick does
        not stack up overlapping runs.

        Args:
            func: Zero-argument coroutine factory invoked on each tick.
            minutes: Interval between successive runs.
            job_id: Stable identifier; passing the same id replaces the
                previous registration so a config reload does not leave
                stale jobs around.
        """
        self._scheduler.add_job(
            func,
            trigger="interval",
            minutes=minutes,
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _logger.info(
            "[scheduler] Registered interval job",
            job_id=job_id,
            minutes=minutes,
        )

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

        Opens a ``scan_runs`` row tagged ``trigger='scheduled'`` so
        admin history surfaces background runs alongside
        manually-triggered ones, then delegates to ``ScanRunService``
        which writes the terminal state and emits log lines.
        """
        _logger.info("[scheduler] Running scan", library_id=library_id)

        library = await self._load_library(library_id)
        if library is None:
            return

        run = await self._scan_run_service.open_scan(
            library_id=library_id,
            trigger=ScanRunTrigger.SCHEDULED,
        )
        if run.id is None:  # pragma: no cover — repo always assigns
            _logger.error(
                "[scheduler] open_scan returned a row without id; skipping",
                library_id=library_id,
            )
            return

        await self._scan_run_service.run_scan(run.id, library)
        await self._mark_library_scanned(library_id)

    async def _load_library(self, library_id: str) -> Library | None:
        """Return the library row, or ``None`` if it vanished."""
        async with self._library_uow_factory() as uow:
            library = await uow.libraries.find_by_id(LibraryId(library_id))
            if library is None:
                _logger.warning(
                    "[scheduler] Library vanished before scan; skipping",
                    library_id=library_id,
                )
                return None
            return library

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
