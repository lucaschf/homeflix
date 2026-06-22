"""Tests for TriggerJobUseCase (admin "run now")."""

import pytest

from src.modules.media.application.dtos.job_dtos import TriggerJobInput
from src.modules.media.application.ports import SchedulerControlPort
from src.modules.media.application.use_cases.trigger_job import (
    JobNotScheduledError,
    TriggerJobUseCase,
)


class _FakeControl(SchedulerControlPort):
    def __init__(self, *, found: bool) -> None:
        self._found = found
        self.triggered: list[str] = []

    def trigger(self, job_id: str) -> bool:
        self.triggered.append(job_id)
        return self._found


@pytest.mark.unit
class TestTriggerJob:
    @pytest.mark.asyncio
    async def test_triggers_registered_job(self) -> None:
        control = _FakeControl(found=True)
        use_case = TriggerJobUseCase(scheduler_control=control)

        await use_case.execute(TriggerJobInput(job_id="homeflix:thumbnail-backfill"))

        assert control.triggered == ["homeflix:thumbnail-backfill"]

    @pytest.mark.asyncio
    async def test_raises_when_job_not_scheduled(self) -> None:
        control = _FakeControl(found=False)
        use_case = TriggerJobUseCase(scheduler_control=control)

        with pytest.raises(JobNotScheduledError) as excinfo:
            await use_case.execute(TriggerJobInput(job_id="ghost"))

        assert excinfo.value.job_id == "ghost"
