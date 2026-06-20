"""ListJobRunsUseCase — paginated job execution history."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.media.application.use_cases._to_job_run_output import job_run_to_output

if TYPE_CHECKING:
    from src.modules.media.application.dtos.job_dtos import JobRunOutput, ListJobRunsInput
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory


class ListJobRunsUseCase:
    """List recorded job executions newest-first, optionally per job."""

    def __init__(self, media_uow_factory: MediaUnitOfWorkFactory) -> None:
        self._media_uow_factory = media_uow_factory

    async def execute(self, input_dto: ListJobRunsInput) -> list[JobRunOutput]:
        """Return a page of job runs."""
        async with self._media_uow_factory() as uow:
            runs = await uow.job_runs.list_paginated(
                job_id=input_dto.job_id,
                limit=input_dto.limit,
                offset=input_dto.offset,
            )
        return [job_run_to_output(run) for run in runs]


__all__ = ["ListJobRunsUseCase"]
