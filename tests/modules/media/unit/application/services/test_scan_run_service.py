"""Unit tests for ScanRunService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.application.services.scan_run_service import ScanRunService
from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunStatus,
    ScanRunTrigger,
)
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId


def _make_uow_factory(scan_runs_repo: AsyncMock) -> MagicMock:
    """Build an async-context UoW factory whose ``scan_runs`` is the supplied mock."""
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.scan_runs = scan_runs_repo
    factory = MagicMock(return_value=uow)
    return factory


pytestmark = pytest.mark.unit


class TestOpenScan:
    async def test_should_persist_running_row_with_scan_kind(self) -> None:
        scan_runs_repo = AsyncMock()
        saved = ScanRun(
            id=ScanRunId.generate(),
            kind=ScanRunKind.SCAN,
            trigger=ScanRunTrigger.MANUAL,
            library_id="lib_test12345678",
        )
        scan_runs_repo.save.return_value = saved
        service = ScanRunService(
            scan_use_case=AsyncMock(),
            bulk_enrich_use_case=AsyncMock(),
            media_uow_factory=_make_uow_factory(scan_runs_repo),
        )

        result = await service.open_scan(
            library_id="lib_test12345678",
            trigger=ScanRunTrigger.MANUAL,
        )

        assert result is saved
        scan_runs_repo.save.assert_awaited_once()
        opened = scan_runs_repo.save.await_args.args[0]
        assert opened.kind == ScanRunKind.SCAN
        assert opened.trigger == ScanRunTrigger.MANUAL
        assert opened.library_id == "lib_test12345678"
        assert opened.status == ScanRunStatus.RUNNING


class TestRunScan:
    async def test_should_persist_succeeded_row_with_summary(self) -> None:
        run_id = ScanRunId.generate()
        existing = ScanRun(
            id=run_id,
            kind=ScanRunKind.SCAN,
            trigger=ScanRunTrigger.MANUAL,
            library_id="lib_test12345678",
        )
        scan_runs_repo = AsyncMock()
        scan_runs_repo.find_by_id.return_value = existing

        scan_uc = AsyncMock()
        scan_uc.execute.return_value = MagicMock(
            movies_created=2,
            movies_updated=1,
            episodes_created=0,
            episodes_updated=0,
            errors=["err1"],
        )
        library = MagicMock(id="lib_test12345678", paths=["/movies"])

        service = ScanRunService(
            scan_use_case=scan_uc,
            bulk_enrich_use_case=AsyncMock(),
            media_uow_factory=_make_uow_factory(scan_runs_repo),
        )
        await service.run_scan(run_id, library)

        scan_runs_repo.save.assert_awaited_once()
        saved = scan_runs_repo.save.await_args.args[0]
        assert saved.status == ScanRunStatus.SUCCEEDED
        assert saved.summary == {
            "movies_created": 2,
            "movies_updated": 1,
            "episodes_created": 0,
            "episodes_updated": 0,
        }
        assert saved.errors == ["err1"]

    async def test_should_persist_failed_row_on_crash(self) -> None:
        run_id = ScanRunId.generate()
        existing = ScanRun(
            id=run_id,
            kind=ScanRunKind.SCAN,
            trigger=ScanRunTrigger.MANUAL,
            library_id="lib_test12345678",
        )
        scan_runs_repo = AsyncMock()
        scan_runs_repo.find_by_id.return_value = existing

        scan_uc = AsyncMock()
        scan_uc.execute.side_effect = RuntimeError("ffmpeg exploded")
        library = MagicMock(id="lib_test12345678", paths=["/movies"])

        service = ScanRunService(
            scan_use_case=scan_uc,
            bulk_enrich_use_case=AsyncMock(),
            media_uow_factory=_make_uow_factory(scan_runs_repo),
        )
        await service.run_scan(run_id, library)

        saved = scan_runs_repo.save.await_args.args[0]
        assert saved.status == ScanRunStatus.FAILED
        assert "ffmpeg exploded" in saved.errors[0]


class TestRunBulkEnrich:
    async def test_should_persist_succeeded_row_with_enrich_summary(self) -> None:
        run_id = ScanRunId.generate()
        existing = ScanRun(
            id=run_id,
            kind=ScanRunKind.ENRICH,
            trigger=ScanRunTrigger.MANUAL,
        )
        scan_runs_repo = AsyncMock()
        scan_runs_repo.find_by_id.return_value = existing

        enrich_uc = AsyncMock()
        enrich_uc.execute.return_value = MagicMock(
            movies_enriched=4,
            series_enriched=2,
            skipped=1,
            errors=[],
        )

        service = ScanRunService(
            scan_use_case=AsyncMock(),
            bulk_enrich_use_case=enrich_uc,
            media_uow_factory=_make_uow_factory(scan_runs_repo),
        )
        await service.run_bulk_enrich(run_id, force=False)

        saved = scan_runs_repo.save.await_args.args[0]
        assert saved.status == ScanRunStatus.SUCCEEDED
        assert saved.summary == {
            "movies_enriched": 4,
            "series_enriched": 2,
            "skipped": 1,
        }
