"""Tests for ScanDedupSweepJob (ADR-015 Phase 6.5)."""

from unittest.mock import AsyncMock

import pytest

from src.infrastructure.scheduling.scan_dedup_sweep_job import ScanDedupSweepJob
from src.modules.media.application.dtos.conflict_dtos import (
    SweepMovieConflictsOutput,
)
from src.modules.settings.domain.value_objects import ScanDedupConfig


@pytest.mark.asyncio
async def test_run_invokes_sweep_when_enabled() -> None:
    sweep = AsyncMock()
    sweep.execute.return_value = SweepMovieConflictsOutput(
        movies_scanned=3,
        conflicts_created=1,
        conflict_ids=["cnf_abc12345abcd"],
    )
    runtime_settings = AsyncMock()
    runtime_settings.scan_dedup.return_value = ScanDedupConfig(sweep_enabled=True)

    job = ScanDedupSweepJob(sweep_use_case=sweep, runtime_settings=runtime_settings)
    await job.run()

    sweep.execute.assert_awaited_once()
    runtime_settings.scan_dedup.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_skips_sweep_when_disabled() -> None:
    sweep = AsyncMock()
    runtime_settings = AsyncMock()
    runtime_settings.scan_dedup.return_value = ScanDedupConfig(sweep_enabled=False)

    job = ScanDedupSweepJob(sweep_use_case=sweep, runtime_settings=runtime_settings)
    await job.run()

    sweep.execute.assert_not_called()
