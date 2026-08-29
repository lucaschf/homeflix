"""Tests for BackgroundIntroDetectionRunner.

The adapter is deliberately thin: it owns the fire-and-forget task and
the one-run-per-season guard, so these tests drive a fake job whose
completion the test controls.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.modules.media.domain.value_objects import SeasonId
from src.modules.media.infrastructure.scheduling.intro_detection_runner import (
    BackgroundIntroDetectionRunner,
)


class _BlockingJob:
    """Job stub whose ``run_for_season`` finishes only when released."""

    def __init__(self) -> None:
        self.released = asyncio.Event()
        self.started = asyncio.Event()
        self.calls: list[SeasonId] = []

    async def run_for_season(self, season_id: SeasonId) -> None:
        self.calls.append(season_id)
        self.started.set()
        await self.released.wait()


@pytest.mark.unit
class TestBackgroundIntroDetectionRunner:
    @pytest.mark.asyncio
    async def test_runs_the_job_for_the_season_off_the_caller_stack(self) -> None:
        job = AsyncMock()
        runner = BackgroundIntroDetectionRunner(job=job)  # type: ignore[arg-type]
        season_id = SeasonId.generate()

        assert runner.start_for_season(season_id) is True
        # Not awaited by the caller — the job only advances once the
        # event loop gets control back.
        job.run_for_season.assert_not_awaited()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        job.run_for_season.assert_awaited_once_with(season_id)

    @pytest.mark.asyncio
    async def test_refuses_a_second_run_while_one_is_in_flight(self) -> None:
        job = _BlockingJob()
        runner = BackgroundIntroDetectionRunner(job=job)  # type: ignore[arg-type]
        season_id = SeasonId.generate()

        assert runner.start_for_season(season_id) is True
        await job.started.wait()
        assert runner.start_for_season(season_id) is False

        job.released.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert job.calls == [season_id]

    @pytest.mark.asyncio
    async def test_allows_concurrent_runs_for_different_seasons(self) -> None:
        job = _BlockingJob()
        runner = BackgroundIntroDetectionRunner(job=job)  # type: ignore[arg-type]
        first = SeasonId.generate()
        second = SeasonId.generate()

        assert runner.start_for_season(first) is True
        assert runner.start_for_season(second) is True

        job.released.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert sorted(str(s) for s in job.calls) == sorted([str(first), str(second)])

    @pytest.mark.asyncio
    async def test_releases_the_slot_after_a_run_finishes(self) -> None:
        job = _BlockingJob()
        runner = BackgroundIntroDetectionRunner(job=job)  # type: ignore[arg-type]
        season_id = SeasonId.generate()

        assert runner.start_for_season(season_id) is True
        job.released.set()
        for _ in range(4):
            await asyncio.sleep(0)

        assert runner.start_for_season(season_id) is True

    @pytest.mark.asyncio
    async def test_releases_the_slot_when_the_run_crashes(self) -> None:
        job = AsyncMock()
        job.run_for_season = AsyncMock(side_effect=RuntimeError("db gone"))
        runner = BackgroundIntroDetectionRunner(job=job)  # type: ignore[arg-type]
        season_id = SeasonId.generate()

        assert runner.start_for_season(season_id) is True
        for _ in range(4):
            await asyncio.sleep(0)

        # The crash is swallowed and logged; the season is startable again.
        assert runner.start_for_season(season_id) is True
