"""Unit tests for ListScanRunsUseCase and GetScanRunUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.scan_run_dtos import (
    GetScanRunInput,
    ListScanRunsInput,
)
from src.modules.media.application.use_cases.get_scan_run import GetScanRunUseCase
from src.modules.media.application.use_cases.list_scan_runs import ListScanRunsUseCase
from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
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


class TestListScanRunsUseCase:
    async def test_should_project_runs_to_output_dtos(self) -> None:
        repo = AsyncMock()
        repo.list_paginated.return_value = [
            ScanRun(
                id=ScanRunId.generate(),
                kind=ScanRunKind.SCAN,
                trigger=ScanRunTrigger.MANUAL,
                library_id="lib_test12345678",
            ),
        ]

        result = await ListScanRunsUseCase(
            media_uow_factory=_build_uow_factory(repo),
        ).execute(ListScanRunsInput(kind="scan"))

        assert len(result) == 1
        assert result[0].kind == "scan"
        assert result[0].status == "running"
        repo.list_paginated.assert_awaited_once()
        kwargs = repo.list_paginated.await_args.kwargs
        assert kwargs["kind"] == ScanRunKind.SCAN


class TestGetScanRunUseCase:
    async def test_should_return_run_when_found(self) -> None:
        run_id = ScanRunId.generate()
        repo = AsyncMock()
        repo.find_by_id.return_value = ScanRun(
            id=run_id,
            kind=ScanRunKind.ENRICH,
            trigger=ScanRunTrigger.MANUAL,
        )

        result = await GetScanRunUseCase(
            media_uow_factory=_build_uow_factory(repo),
        ).execute(GetScanRunInput(run_id=str(run_id)))

        assert result.id == str(run_id)
        assert result.kind == "enrich"

    async def test_should_raise_when_not_found(self) -> None:
        repo = AsyncMock()
        repo.find_by_id.return_value = None

        with pytest.raises(ResourceNotFoundException):
            await GetScanRunUseCase(
                media_uow_factory=_build_uow_factory(repo),
            ).execute(GetScanRunInput(run_id=str(ScanRunId.generate())))
