"""ListScanRunsUseCase — paginated scan/enrich history for the admin page."""

from src.modules.media.application.dtos.scan_run_dtos import (
    ListScanRunsInput,
    ScanRunOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._to_scan_run_output import (
    scan_run_to_output,
)
from src.modules.media.domain.entities.scan_run import ScanRunKind, ScanRunTrigger


class ListScanRunsUseCase:
    """Page through ``scan_runs`` newest-first, optionally narrowed.

    The page caps at 50 rows — the admin Scan / Enrich screens
    render this as a flat table without virtualised scrolling, so
    keep the result set scannable.
    """

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def execute(self, input_dto: ListScanRunsInput) -> list[ScanRunOutput]:
        """Return the requested page of run rows."""
        kind = ScanRunKind(input_dto.kind) if input_dto.kind else None
        trigger = ScanRunTrigger(input_dto.trigger) if input_dto.trigger else None

        async with self._media_uow_factory() as uow:
            runs = await uow.scan_runs.list_paginated(
                kind=kind,
                trigger=trigger,
                library_id=input_dto.library_id,
                limit=input_dto.limit,
                offset=input_dto.offset,
            )
        return [scan_run_to_output(r) for r in runs]


__all__ = ["ListScanRunsUseCase"]
