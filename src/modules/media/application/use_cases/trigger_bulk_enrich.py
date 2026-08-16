"""TriggerBulkEnrichUseCase — admin fires a background metadata refresh."""

import asyncio
import logging
from typing import Any

from src.modules.media.application.dtos.scan_run_dtos import (
    ScanRunOutput,
    TriggerBulkEnrichInput,
)
from src.modules.media.application.services.scan_run_service import ScanRunService
from src.modules.media.application.use_cases._to_scan_run_output import (
    scan_run_to_output,
)
from src.modules.media.domain.entities.scan_run import ScanRunTrigger

_logger = logging.getLogger(__name__)


class TriggerBulkEnrichUseCase:
    """Open an ``enrich`` ``scan_runs`` row and spawn the work in the background.

    Bulk enrich today is global (every movie + series with missing
    metadata) rather than library-scoped. The history row keeps
    ``library_id=None`` to reflect that — the operator gets a
    single row for "I asked TMDB to backfill everything at 14:32".
    """

    def __init__(self, scan_run_service: ScanRunService) -> None:
        self._service = scan_run_service

    async def execute(self, input_dto: TriggerBulkEnrichInput) -> ScanRunOutput:
        """Open the row, schedule the enrich, return immediately."""
        trigger = ScanRunTrigger(input_dto.trigger)
        run = await self._service.open_bulk_enrich(trigger=trigger)

        if run.id is None:  # pragma: no cover
            raise RuntimeError("open_bulk_enrich returned a row without id")

        task = asyncio.create_task(
            self._service.run_bulk_enrich(run.id, input_dto.force),
            name=f"enrich-run-{run.id}",
        )
        task.add_done_callback(_log_task_failure)
        return scan_run_to_output(run)


def _log_task_failure(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        _logger.info("Enrich task %s was cancelled", task.get_name())
        return
    exc = task.exception()
    if exc is not None:
        _logger.exception(
            "Enrich task %s exited unexpectedly: %s",
            task.get_name(),
            exc,
            exc_info=exc,
        )


__all__ = ["TriggerBulkEnrichUseCase"]
