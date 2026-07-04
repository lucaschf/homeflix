"""ListSubtitleOcrRunsUseCase — audit history of subtitle-OCR runs."""

from src.modules.media.application.dtos.subtitle_ocr_run_dtos import (
    ListSubtitleOcrRunsInput,
    SubtitleOcrRunOutput,
    subtitle_ocr_run_to_output,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory


class ListSubtitleOcrRunsUseCase:
    """Return subtitle-OCR run records newest-first, with filters."""

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def execute(
        self,
        input_dto: ListSubtitleOcrRunsInput,
    ) -> list[SubtitleOcrRunOutput]:
        """Return matching runs newest-first as output DTOs."""
        async with self._media_uow_factory() as uow:
            runs = await uow.subtitle_ocr_runs.list_paginated(
                media_kind=input_dto.media_kind,
                media_id=input_dto.media_id,
                limit=input_dto.limit,
                offset=input_dto.offset,
            )
        return [subtitle_ocr_run_to_output(run) for run in runs]


__all__ = ["ListSubtitleOcrRunsUseCase"]
