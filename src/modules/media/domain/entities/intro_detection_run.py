"""IntroDetectionRun aggregate — per-season intro-detection audit row.

One row is appended each time the detection job processes a season, so
operators can see *why* a tick produced (or dropped) markers — counts
plus per-episode confidences and whether each was persisted. Append-only:
records are never mutated after the season is processed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.building_blocks.domain import AggregateRoot, CompoundValueObject
from src.modules.media.domain.value_objects.intro_detection_run_id import IntroDetectionRunId
from src.modules.media.domain.value_objects.intro_detection_state import (
    IntroDetectionState,  # noqa: TCH001 — runtime field type (pydantic resolves it)
)


class EpisodeDetectionResult(CompoundValueObject):
    """One episode's detection outcome within a run.

    Attributes:
        episode_id: External id of the episode (epi_xxx).
        episode_number: Episode number within the season.
        start_seconds: Detected intro start.
        end_seconds: Detected intro end.
        confidence: Detector confidence in ``[0.0, 1.0]`` — the same range
            the IntroMarker/CreditsMarker VOs enforce, so a stray detector
            value can't be recorded in the append-only audit log.
        persisted: Whether the marker was saved. ``False`` means the
            confidence fell below the configured ``min_confidence`` and
            the detection was dropped — the common "detected but nothing
            showed up" case.
    """

    episode_id: str
    episode_number: int
    start_seconds: float
    end_seconds: float
    confidence: float = Field(ge=0.0, le=1.0)
    persisted: bool


class IntroDetectionRun(AggregateRoot[IntroDetectionRunId]):
    """A single season's intro-detection run record.

    Attributes:
        series_id: External id of the parent series (ser_xxx).
        series_title: Series title, denormalized at write time so the
            audit row stays self-contained (survives rename/delete).
        season_id: External id of the season processed (ssn_xxx).
        season_number: Season number, denormalized for display.
        algorithm: Detector used (``chromaprint`` | ``frame_hash``).
        outcome: Terminal season state — ``COMPLETED``,
            ``INSUFFICIENT_EPISODES``, or ``FAILED``.
        ref_count: Episodes handed to the detector (non-MANUAL, with a
            primary file).
        analyzed_count: Episodes the detector could extract signal from.
        detected_count: Episodes the detector produced a marker for
            (before the confidence floor).
        persisted_count: Markers actually saved (confidence ≥
            ``min_confidence``).
        min_confidence: Confidence floor applied on this run.
        episode_results: Per-episode detection detail (including dropped
            ones, with their confidence).
        error: Failure message when ``outcome`` is ``FAILED``.
        started_at: When the season's processing began.
        finished_at: When the run was recorded.
    """

    id: IntroDetectionRunId | None = Field(default=None)
    series_id: str
    series_title: str = ""
    season_id: str
    season_number: int
    algorithm: str
    outcome: IntroDetectionState
    ref_count: int = 0
    analyzed_count: int = 0
    detected_count: int = 0
    persisted_count: int = 0
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    episode_results: list[EpisodeDetectionResult] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["EpisodeDetectionResult", "IntroDetectionRun"]
