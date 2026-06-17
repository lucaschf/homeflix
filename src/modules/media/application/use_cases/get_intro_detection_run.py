"""GetIntroDetectionRunUseCase — fetch a single intro-detection run."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.intro_detection_run_dtos import (
    GetIntroDetectionRunInput,
    IntroDetectionRunOutput,
    intro_detection_run_to_output,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects.intro_detection_run_id import IntroDetectionRunId


class GetIntroDetectionRunUseCase:
    """Fetch one intro-detection run by id, with full per-episode detail."""

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def execute(self, input_dto: GetIntroDetectionRunInput) -> IntroDetectionRunOutput:
        """Return the run with the given id, or raise if absent."""
        run_id = IntroDetectionRunId(input_dto.run_id)
        async with self._media_uow_factory() as uow:
            run = await uow.intro_detection_runs.find_by_id(run_id)
        if run is None:
            raise ResourceNotFoundException.for_resource("IntroDetectionRun", input_dto.run_id)
        return intro_detection_run_to_output(run)


__all__ = ["GetIntroDetectionRunUseCase"]
