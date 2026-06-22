"""TriggerJobUseCase — admin runs a scheduled background job now."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.media.application.dtos.job_dtos import TriggerJobInput
    from src.modules.media.application.ports import SchedulerControlPort


class JobNotScheduledError(Exception):
    """Admin asked to run a job that isn't currently registered.

    Either the job id is unknown, or it only exists in history (e.g. a
    library whose schedule was removed). Such jobs cannot be triggered
    because the scheduler has nothing registered to fire.
    """

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job {job_id} is not currently scheduled")
        self.job_id = job_id


class TriggerJobUseCase:
    """Reschedule a registered scheduler job to run immediately.

    The job runs through its normal recorded wrapper, so the manual run
    shows up in the Jobs dashboard (running → succeeded/failed) exactly
    like a scheduled tick. The cadence is unaffected: APScheduler
    recomputes the next scheduled run after the manual fire.
    """

    def __init__(self, scheduler_control: SchedulerControlPort) -> None:
        self._control = scheduler_control

    async def execute(self, input_dto: TriggerJobInput) -> None:
        """Trigger ``job_id`` now, or raise if it isn't scheduled."""
        if not self._control.trigger(input_dto.job_id):
            raise JobNotScheduledError(input_dto.job_id)


__all__ = ["JobNotScheduledError", "TriggerJobUseCase"]
