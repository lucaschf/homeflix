"""Unit tests for SweepInterruptedScanRunsUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.application.use_cases.sweep_interrupted_scan_runs import (
    SweepInterruptedScanRunsUseCase,
)
from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunStatus,
    ScanRunTrigger,
)
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId


def _build_uow_factory(scan_runs_repo: AsyncMock) -> MagicMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.scan_runs = scan_runs_repo
    return MagicMock(return_value=uow)


pytestmark = pytest.mark.unit


class TestSweepInterruptedScanRunsUseCase:
    async def test_should_transition_every_running_row_to_interrupted(self) -> None:
        repo = AsyncMock()
        repo.list_by_status.return_value = [
            ScanRun(
                id=ScanRunId.generate(),
                kind=ScanRunKind.SCAN,
                trigger=ScanRunTrigger.MANUAL,
                library_id="lib_test12345678",
            ),
            ScanRun(
                id=ScanRunId.generate(),
                kind=ScanRunKind.ENRICH,
                trigger=ScanRunTrigger.SCHEDULED,
                library_id=None,
            ),
        ]

        count = await SweepInterruptedScanRunsUseCase(
            media_uow_factory=_build_uow_factory(repo),
        ).execute()

        assert count == 2
        assert repo.save.await_count == 2
        for call in repo.save.await_args_list:
            saved = call.args[0]
            assert saved.status == ScanRunStatus.INTERRUPTED
            assert saved.finished_at is not None

    async def test_should_be_noop_when_no_running_rows(self) -> None:
        repo = AsyncMock()
        repo.list_by_status.return_value = []

        count = await SweepInterruptedScanRunsUseCase(
            media_uow_factory=_build_uow_factory(repo),
        ).execute()

        assert count == 0
        repo.save.assert_not_awaited()
