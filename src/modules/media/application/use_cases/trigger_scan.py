"""TriggerScanUseCase — admin starts a fire-and-forget library scan."""

import asyncio
import logging

from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory
from src.modules.media.application.dtos.scan_run_dtos import (
    ScanRunOutput,
    TriggerScanInput,
)
from src.modules.media.application.services.scan_run_service import ScanRunService
from src.modules.media.application.use_cases._to_scan_run_output import (
    scan_run_to_output,
)
from src.modules.media.domain.entities.scan_run import ScanRunTrigger
from src.shared_kernel.value_objects.library_id import LibraryId

_logger = logging.getLogger(__name__)


class LibraryNotFoundForScanError(Exception):
    """Admin POSTed a scan for a library id that doesn't exist."""

    def __init__(self, library_id: str) -> None:
        super().__init__(f"Library {library_id} not found")
        self.library_id = library_id


class TriggerScanUseCase:
    """Open a ``scan_runs`` row + fire the scan as a background task.

    Synchronous wait-for-completion was the v0 behaviour
    (``POST /api/v1/scan`` blocks for tens of seconds on large
    libraries). v1 returns immediately with the run id; the
    admin Scan page polls ``GET /api/v1/admin/scans/{id}`` for
    progress.
    """

    def __init__(
        self,
        scan_run_service: ScanRunService,
        library_uow_factory: LibraryUnitOfWorkFactory,
    ) -> None:
        self._service = scan_run_service
        self._library_uow_factory = library_uow_factory

    async def execute(self, input_dto: TriggerScanInput) -> ScanRunOutput:
        """Validate the library, open the row, schedule the work."""
        async with self._library_uow_factory() as luow:
            library = await luow.libraries.find_by_id(LibraryId(input_dto.library_id))
        if library is None:
            raise LibraryNotFoundForScanError(input_dto.library_id)

        trigger = ScanRunTrigger(input_dto.trigger)
        run = await self._service.open_scan(
            library_id=str(library.id),
            trigger=trigger,
        )

        if run.id is None:  # pragma: no cover — repo always assigns
            raise RuntimeError("open_scan returned a row without id")

        # Spawn the actual scan as a background task. We deliberately
        # do *not* await it — the admin page would time out on a
        # 30-second scan if we did, and the row is the durable
        # record for the operator to poll against. Failures inside
        # run_scan write themselves to the row's terminal state.
        task = asyncio.create_task(
            self._service.run_scan(run.id, library),
            name=f"scan-run-{run.id}",
        )
        task.add_done_callback(_log_task_failure)
        return scan_run_to_output(run)


def _log_task_failure(task: asyncio.Task) -> None:
    """Surface unexpected task crashes in the logs.

    Normal failure paths inside ``ScanRunService.run_scan`` write
    the error to the row and don't re-raise. Anything that lands
    here is a programmer error (e.g. cancellation) we want to see.
    """
    if task.cancelled():
        _logger.info("Scan task %s was cancelled", task.get_name())
        return
    exc = task.exception()
    if exc is not None:
        _logger.exception(
            "Scan task %s exited unexpectedly: %s",
            task.get_name(),
            exc,
            exc_info=exc,
        )


__all__ = ["LibraryNotFoundForScanError", "TriggerScanUseCase"]
