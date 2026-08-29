"""Tests for ResetSeasonIntroDetectionUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.intro_dtos import ResetSeasonIntroDetectionInput
from src.modules.media.application.use_cases.reset_season_intro_detection import (
    ResetSeasonIntroDetectionUseCase,
)
from src.modules.media.domain.value_objects import IntroDetectionState, SeasonId


def _build_uow(*, season_found: bool, cleared: int = 0) -> AsyncMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.series = AsyncMock()
    uow.series.update_season_intro_detection = AsyncMock(return_value=season_found)
    uow.series.clear_auto_intro_markers_for_season = AsyncMock(return_value=cleared)
    return uow


def _build_runner(*, started: bool = True) -> MagicMock:
    runner = MagicMock()
    runner.start_for_season = MagicMock(return_value=started)
    return runner


@pytest.mark.unit
class TestResetSeasonIntroDetectionUseCase:
    @pytest.mark.asyncio
    async def test_requeues_season_and_clears_auto_markers(self) -> None:
        season_id = SeasonId.generate()
        uow = _build_uow(season_found=True, cleared=3)
        use_case = ResetSeasonIntroDetectionUseCase(
            uow_factory=MagicMock(return_value=uow),
            detection_runner=_build_runner(),
        )

        result = await use_case.execute(ResetSeasonIntroDetectionInput(season_id=str(season_id)))

        assert result.markers_cleared == 3
        state_call = uow.series.update_season_intro_detection.await_args
        assert state_call.args[1] == IntroDetectionState.NOT_STARTED
        assert state_call.kwargs["attempted_at"] is None
        uow.series.clear_auto_intro_markers_for_season.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_when_season_not_found(self) -> None:
        uow = _build_uow(season_found=False)
        use_case = ResetSeasonIntroDetectionUseCase(
            uow_factory=MagicMock(return_value=uow),
            detection_runner=_build_runner(),
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                ResetSeasonIntroDetectionInput(season_id=str(SeasonId.generate()))
            )

        uow.series.clear_auto_intro_markers_for_season.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_start_detection_by_default(self) -> None:
        uow = _build_uow(season_found=True)
        runner = _build_runner()
        use_case = ResetSeasonIntroDetectionUseCase(
            uow_factory=MagicMock(return_value=uow),
            detection_runner=runner,
        )

        result = await use_case.execute(
            ResetSeasonIntroDetectionInput(season_id=str(SeasonId.generate()))
        )

        assert result.detection_started is False
        runner.start_for_season.assert_not_called()

    @pytest.mark.asyncio
    async def test_starts_detection_when_run_now_requested(self) -> None:
        season_id = SeasonId.generate()
        uow = _build_uow(season_found=True, cleared=2)
        runner = _build_runner(started=True)
        use_case = ResetSeasonIntroDetectionUseCase(
            uow_factory=MagicMock(return_value=uow),
            detection_runner=runner,
        )

        result = await use_case.execute(
            ResetSeasonIntroDetectionInput(season_id=str(season_id), run_now=True)
        )

        assert result.detection_started is True
        assert result.markers_cleared == 2
        assert runner.start_for_season.call_args.args[0] == season_id

    @pytest.mark.asyncio
    async def test_reports_not_started_when_a_run_is_already_in_flight(self) -> None:
        uow = _build_uow(season_found=True)
        runner = _build_runner(started=False)
        use_case = ResetSeasonIntroDetectionUseCase(
            uow_factory=MagicMock(return_value=uow),
            detection_runner=runner,
        )

        result = await use_case.execute(
            ResetSeasonIntroDetectionInput(season_id=str(SeasonId.generate()), run_now=True)
        )

        assert result.detection_started is False

    @pytest.mark.asyncio
    async def test_does_not_start_detection_for_a_missing_season(self) -> None:
        uow = _build_uow(season_found=False)
        runner = _build_runner()
        use_case = ResetSeasonIntroDetectionUseCase(
            uow_factory=MagicMock(return_value=uow),
            detection_runner=runner,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                ResetSeasonIntroDetectionInput(season_id=str(SeasonId.generate()), run_now=True)
            )

        runner.start_for_season.assert_not_called()
