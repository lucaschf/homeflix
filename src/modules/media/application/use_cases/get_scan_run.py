"""GetScanRunUseCase — admin detail view for a single run."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.scan_run_dtos import (
    GetScanRunInput,
    ScanRunOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._to_scan_run_output import (
    scan_run_to_output,
)
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId


class GetScanRunUseCase:
    """Hydrate a single ``scan_runs`` row by external id.

    Drives the admin detail page (used by both Scan and Enrich
    screens after the operator clicks a row) and the polling loop
    on the trigger UX — the frontend hits this endpoint every few
    seconds while ``status == "running"``.
    """

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def execute(self, input_dto: GetScanRunInput) -> ScanRunOutput:
        """Return the run or raise ``ResourceNotFoundException``."""
        run_id = ScanRunId(input_dto.run_id)
        async with self._media_uow_factory() as uow:
            run = await uow.scan_runs.find_by_id(run_id)
        if run is None:
            raise ResourceNotFoundException.for_resource("ScanRun", input_dto.run_id)
        return scan_run_to_output(run)


__all__ = ["GetScanRunUseCase"]
