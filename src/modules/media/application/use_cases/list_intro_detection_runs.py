"""ListIntroDetectionRunsUseCase — audit history of intro-detection runs."""

from src.modules.media.application.dtos.intro_detection_run_dtos import (
    IntroDetectionRunOutput,
    ListIntroDetectionRunsInput,
    intro_detection_run_to_output,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory


class ListIntroDetectionRunsUseCase:
    """Return intro-detection run records newest-first, with filters."""

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def execute(
        self,
        input_dto: ListIntroDetectionRunsInput,
    ) -> list[IntroDetectionRunOutput]:
        """Return matching runs newest-first as output DTOs."""
        async with self._media_uow_factory() as uow:
            runs = await uow.intro_detection_runs.list_paginated(
                season_id=input_dto.season_id,
                series_id=input_dto.series_id,
                limit=input_dto.limit,
                offset=input_dto.offset,
            )
        return [intro_detection_run_to_output(run) for run in runs]


__all__ = ["ListIntroDetectionRunsUseCase"]
