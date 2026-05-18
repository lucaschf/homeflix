"""SweepInterruptedScanRunsUseCase — startup hook to repair orphan ``running`` rows."""

import logging

from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities.scan_run import ScanRunStatus

_logger = logging.getLogger(__name__)


class SweepInterruptedScanRunsUseCase:
    """Mark every ``running`` ``scan_runs`` row as ``interrupted``.

    Runs once during ``lifespan`` startup. If the process was
    killed while a scan or bulk enrich was in flight, the row
    would otherwise stay in ``running`` forever and the admin
    page would show a perpetually-active job that never finishes.
    Re-running the scan is the operator's call; the sweeper just
    closes the row so the listing is honest about state.
    """

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def execute(self) -> int:
        """Sweep + return the number of rows transitioned."""
        async with self._media_uow_factory() as uow:
            running = await uow.scan_runs.list_by_status(ScanRunStatus.RUNNING)
            for run in running:
                await uow.scan_runs.save(run.mark_interrupted())

        if running:
            _logger.warning(
                "Marked %d orphan scan_runs as 'interrupted' on startup. "
                "Re-run the scan/enrich manually if needed.",
                len(running),
            )
        return len(running)


__all__ = ["SweepInterruptedScanRunsUseCase"]
