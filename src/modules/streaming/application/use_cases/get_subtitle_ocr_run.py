"""GetSubtitleOcrRunUseCase — fetch a single subtitle-OCR run."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.streaming.application.dtos.subtitle_ocr_run_dtos import (
    GetSubtitleOcrRunInput,
    SubtitleOcrRunOutput,
    subtitle_ocr_run_to_output,
)
from src.modules.streaming.application.unit_of_work import StreamingUnitOfWorkFactory
from src.modules.streaming.domain.value_objects.subtitle_ocr_run_id import SubtitleOcrRunId


class GetSubtitleOcrRunUseCase:
    """Fetch one subtitle-OCR run by id, with full per-track detail."""

    def __init__(self, uow_factory: StreamingUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: GetSubtitleOcrRunInput) -> SubtitleOcrRunOutput:
        """Return the run with the given id, or raise if absent."""
        run_id = SubtitleOcrRunId(input_dto.run_id)
        async with self._uow_factory() as uow:
            run = await uow.subtitle_ocr_runs.find_by_id(run_id)
        if run is None:
            raise ResourceNotFoundException.for_resource("SubtitleOcrRun", input_dto.run_id)
        return subtitle_ocr_run_to_output(run)


__all__ = ["GetSubtitleOcrRunUseCase"]
