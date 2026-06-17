"""Tests for the intro-detection run (audit) use cases."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.intro_detection_run_dtos import (
    GetIntroDetectionRunInput,
    ListIntroDetectionRunsInput,
)
from src.modules.media.application.use_cases.get_intro_detection_run import (
    GetIntroDetectionRunUseCase,
)
from src.modules.media.application.use_cases.list_intro_detection_runs import (
    ListIntroDetectionRunsUseCase,
)
from src.modules.media.domain.entities.intro_detection_run import (
    EpisodeDetectionResult,
    IntroDetectionRun,
)
from src.modules.media.domain.value_objects import IntroDetectionState
from src.modules.media.domain.value_objects.intro_detection_run_id import IntroDetectionRunId


def _run() -> IntroDetectionRun:
    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    return IntroDetectionRun(
        id=IntroDetectionRunId.generate(),
        series_id="ser_test00000001",
        season_id="ssn_test00000001",
        season_number=1,
        algorithm="frame_hash",
        outcome=IntroDetectionState.COMPLETED,
        ref_count=3,
        analyzed_count=3,
        detected_count=2,
        persisted_count=1,
        min_confidence=0.7,
        episode_results=[
            EpisodeDetectionResult(
                episode_id="epi_aaaaaaaaaaaa",
                episode_number=1,
                start_seconds=0.0,
                end_seconds=60.0,
                confidence=0.62,
                persisted=False,
            ),
        ],
        started_at=now,
        finished_at=now,
    )


def _uow(*, runs: list[IntroDetectionRun] | None = None, found: IntroDetectionRun | None = None):
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.intro_detection_runs = AsyncMock()
    uow.intro_detection_runs.list_paginated = AsyncMock(return_value=runs or [])
    uow.intro_detection_runs.find_by_id = AsyncMock(return_value=found)
    return uow


@pytest.mark.unit
class TestIntroDetectionRunUseCases:
    @pytest.mark.asyncio
    async def test_list_projects_runs_to_output(self) -> None:
        run = _run()
        uow = _uow(runs=[run])
        use_case = ListIntroDetectionRunsUseCase(media_uow_factory=MagicMock(return_value=uow))

        rows = await use_case.execute(ListIntroDetectionRunsInput(season_id="ssn_test00000001"))

        assert len(rows) == 1
        assert rows[0].id == str(run.id)
        assert rows[0].outcome == IntroDetectionState.COMPLETED.value
        assert rows[0].episode_results[0].persisted is False
        uow.intro_detection_runs.list_paginated.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_returns_run_when_found(self) -> None:
        run = _run()
        uow = _uow(found=run)
        use_case = GetIntroDetectionRunUseCase(media_uow_factory=MagicMock(return_value=uow))

        output = await use_case.execute(GetIntroDetectionRunInput(run_id=str(run.id)))

        assert output.id == str(run.id)
        assert output.detected_count == 2

    @pytest.mark.asyncio
    async def test_get_raises_when_not_found(self) -> None:
        uow = _uow(found=None)
        use_case = GetIntroDetectionRunUseCase(media_uow_factory=MagicMock(return_value=uow))

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetIntroDetectionRunInput(run_id=str(IntroDetectionRunId.generate()))
            )
