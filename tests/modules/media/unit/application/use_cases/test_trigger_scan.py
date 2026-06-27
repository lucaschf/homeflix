"""Unit tests for TriggerScanUseCase."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.application.dtos.scan_run_dtos import TriggerScanInput
from src.modules.media.application.ports.library_lookup_port import LibraryRef
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
from src.shared_kernel.value_objects.library_id import LibraryId


def _library_lookup(ref: LibraryRef | None) -> MagicMock:
    port = MagicMock()
    port.find = AsyncMock(return_value=ref)
    return port


pytestmark = pytest.mark.unit


class TestTriggerScanUseCase:
    async def test_should_open_running_row_and_spawn_background_task(self) -> None:
        ref = LibraryRef(id="lib_test12345678", paths=())

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
            library_lookup=_library_lookup(ref),
        )

        result = await use_case.execute(
            TriggerScanInput(library_id="lib_test12345678", trigger="manual"),
        )

        assert result.id == str(opened.id)
        assert result.status == "running"
        service.open_scan.assert_awaited_once_with(
            library_id="lib_test12345678",
            trigger=ScanRunTrigger.MANUAL,
        )
        # Background task is fire-and-forget; let the loop run it.
        await asyncio.sleep(0)
        # The resolved LibraryRef (not a Library aggregate) flows to run_scan.
        service.run_scan.assert_awaited_once_with(opened.id, ref)

    async def test_should_raise_when_library_not_found(self) -> None:
        service = AsyncMock()
        use_case = TriggerScanUseCase(
            scan_run_service=service,
            library_lookup=_library_lookup(None),
        )

        with pytest.raises(LibraryNotFoundForScanError):
            await use_case.execute(
                TriggerScanInput(library_id=str(LibraryId.generate()), trigger="manual"),
            )
        service.open_scan.assert_not_awaited()
