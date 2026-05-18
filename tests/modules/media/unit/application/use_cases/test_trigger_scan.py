"""Unit tests for TriggerScanUseCase."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.library.domain.value_objects.library_id import LibraryId
from src.modules.media.application.dtos.scan_run_dtos import TriggerScanInput
from src.modules.media.application.use_cases.trigger_scan import (
    LibraryNotFoundForScanError,
    TriggerScanUseCase,
)
from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunTrigger,
)
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId


def _build_library_uow_factory(library_repo: AsyncMock) -> MagicMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.libraries = library_repo
    return MagicMock(return_value=uow)


pytestmark = pytest.mark.unit


class TestTriggerScanUseCase:
    async def test_should_open_running_row_and_spawn_background_task(self) -> None:
        library = MagicMock(id="lib_test12345678", paths=["/movies"])
        library_repo = AsyncMock()
        library_repo.find_by_id.return_value = library

        service = AsyncMock()
        opened = ScanRun(
            id=ScanRunId.generate(),
            kind=ScanRunKind.SCAN,
            trigger=ScanRunTrigger.MANUAL,
            library_id="lib_test12345678",
        )
        service.open_scan.return_value = opened
        # Force the background task to complete quickly without doing anything.
        service.run_scan = AsyncMock(return_value=None)

        use_case = TriggerScanUseCase(
            scan_run_service=service,
            library_uow_factory=_build_library_uow_factory(library_repo),
        )

        result = await use_case.execute(
            TriggerScanInput(library_id="lib_test12345678", trigger="manual"),
        )

        assert result.id == str(opened.id)
        assert result.status == "running"
        service.open_scan.assert_awaited_once()
        # Background task is fire-and-forget; let the loop run it.
        await asyncio.sleep(0)
        service.run_scan.assert_awaited_once()

    async def test_should_raise_when_library_not_found(self) -> None:
        library_repo = AsyncMock()
        library_repo.find_by_id.return_value = None

        service = AsyncMock()
        use_case = TriggerScanUseCase(
            scan_run_service=service,
            library_uow_factory=_build_library_uow_factory(library_repo),
        )

        with pytest.raises(LibraryNotFoundForScanError):
            await use_case.execute(
                TriggerScanInput(library_id=str(LibraryId.generate()), trigger="manual"),
            )
        service.open_scan.assert_not_awaited()
