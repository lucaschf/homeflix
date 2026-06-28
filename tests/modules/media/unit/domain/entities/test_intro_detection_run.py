"""Tests for IntroDetectionRun / EpisodeDetectionResult confidence bounds."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.building_blocks.domain import DomainValidationException
from src.modules.media.domain.entities.intro_detection_run import (
    EpisodeDetectionResult,
    IntroDetectionRun,
)
from src.modules.media.domain.value_objects import IntroDetectionState
from src.modules.media.domain.value_objects.intro_detection_run_id import IntroDetectionRunId


def _episode_result(confidence: float) -> EpisodeDetectionResult:
    return EpisodeDetectionResult(
        episode_id="epi_aaaaaaaaaaaa",
        episode_number=1,
        start_seconds=0.0,
        end_seconds=60.0,
        confidence=confidence,
        persisted=False,
    )


def _run(min_confidence: float) -> IntroDetectionRun:
    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    return IntroDetectionRun(
        id=IntroDetectionRunId.generate(),
        series_id="ser_test00000001",
        season_id="ssn_test00000001",
        season_number=1,
        algorithm="frame_hash",
        outcome=IntroDetectionState.COMPLETED,
        min_confidence=min_confidence,
        started_at=now,
        finished_at=now,
    )


@pytest.mark.unit
class TestEpisodeDetectionResultConfidence:
    """confidence must stay within the [0, 1] range the markers enforce."""

    @pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
    def test_accepts_values_in_range(self, confidence: float) -> None:
        assert _episode_result(confidence).confidence == confidence

    @pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0, -1.0, float("nan")])
    def test_rejects_values_out_of_range(self, confidence: float) -> None:
        with pytest.raises(DomainValidationException):
            _episode_result(confidence)


@pytest.mark.unit
class TestIntroDetectionRunMinConfidence:
    """min_confidence is a [0, 1] floor."""

    @pytest.mark.parametrize("min_confidence", [0.0, 0.65, 1.0])
    def test_accepts_values_in_range(self, min_confidence: float) -> None:
        assert _run(min_confidence).min_confidence == min_confidence

    @pytest.mark.parametrize("min_confidence", [-0.01, 1.5, float("nan")])
    def test_rejects_values_out_of_range(self, min_confidence: float) -> None:
        with pytest.raises(DomainValidationException):
            _run(min_confidence)
