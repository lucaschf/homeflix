"""Intro detection tunables — detector selection + per-algorithm buckets."""

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from src.building_blocks.domain.value_objects import CompoundValueObject


class IntroDetectionAlgorithm(StrEnum):
    """Which detector the intro-detection job runs.

    Members:
        CHROMAPRINT: Audio-fingerprint cross-correlation (fpcalc).
            Lightweight — no video decode — but blind to intros whose
            audio theme differs across episodes.
        FRAME_HASH: Video frame perceptual-hashing (dHash) with
            full-offset diagonal voting. Heavier (decodes video) but
            recovers title sequences regardless of a variable-length
            cold open, and is unaffected by per-episode audio mixing.
            The validated-superior default.
    """

    CHROMAPRINT = "chromaprint"
    FRAME_HASH = "frame_hash"


class ChromaprintTuningConfig(CompoundValueObject):
    """Calibration specific to the Chromaprint (audio) detector.

    Attributes:
        max_hash_hamming: Per-hash Hamming-distance ceiling (out of 32
            bits) considered a "match" between two episode fingerprints.
        tolerance_hashes: How many CONSECUTIVE non-matching hashes a run
            can absorb before terminating.
    """

    max_hash_hamming: int = Field(default=10, ge=0, le=32)
    tolerance_hashes: int = Field(default=2, ge=0)


class FrameHashTuningConfig(CompoundValueObject):
    """Calibration specific to the frame-hash (video) detector.

    Attributes:
        hash_distance_threshold: Per-frame Hamming-distance ceiling (out
            of 64 bits) two frames must be within to count as a match.
            Strict by design — loosening it yields spurious matches on
            unrelated frames rather than recovering real intros.
        frame_sample_fps: Frames sampled per second within the analysis
            window. Higher is more precise at the cost of decode time.
        match_tolerance_frames: Consecutive non-matching frames a run
            absorbs before terminating.
        max_gap_seconds: Reserved for callers that merge nearby matched
            blocks before picking the intro.
    """

    hash_distance_threshold: int = Field(default=8, ge=0, le=64)
    frame_sample_fps: float = Field(default=2.0, gt=0.0)
    match_tolerance_frames: int = Field(default=2, ge=0)
    max_gap_seconds: float = Field(default=8.0, ge=0.0)


class IntroDetectionConfig(CompoundValueObject):
    """Operational knobs for the periodic intro-detection job (ADR-014).

    Orchestration knobs live at the top level; algorithm-specific
    calibration is grouped into the ``chromaprint`` / ``frame_hash``
    sub-buckets so each detector's knobs stay together and the active
    one is selected by ``algorithm``.

    Attributes:
        enabled: Toggle for the periodic job. Off by default; requires
            ffmpeg (and ``fpcalc`` for the Chromaprint algorithm).
        algorithm: Which detector to run. Defaults to ``FRAME_HASH``.
        batch_size: Max seasons processed per detection tick. Each
            season decodes/fingerprints every episode, so values above
            2 can saturate the host on large seasons.
        interval_minutes: How often the detection job runs.
        analysis_window_seconds: Leading media (in seconds) analysed per
            episode. 600s (10 min) covers long cold opens plus the title
            sequence; trimming it speeds up the job at the cost of
            missing late-starting intros. Shared by both algorithms.
        min_confidence: Minimum detector confidence in ``[0.0, 1.0]``
            required before an auto-detected intro is persisted.
        min_intro_seconds: Minimum intro length to accept; shorter
            matches are dropped (usually recurring stingers).
        max_intro_seconds: Hard cap on persisted intro length; longer
            detections are truncated.
        chromaprint: Calibration for the Chromaprint detector.
        frame_hash: Calibration for the frame-hash detector.

    Example:
        >>> cfg = IntroDetectionConfig()
        >>> picky = cfg.with_updates(min_confidence=0.85)
    """

    enabled: bool = Field(default=False)
    algorithm: IntroDetectionAlgorithm = Field(default=IntroDetectionAlgorithm.FRAME_HASH)
    batch_size: int = Field(default=1, ge=1)
    interval_minutes: int = Field(default=30, ge=1)
    analysis_window_seconds: int = Field(default=600, ge=60)
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    min_intro_seconds: float = Field(default=5.0, ge=0.0)
    max_intro_seconds: float = Field(default=120.0, ge=10.0)
    chromaprint: ChromaprintTuningConfig = Field(default_factory=ChromaprintTuningConfig)
    frame_hash: FrameHashTuningConfig = Field(default_factory=FrameHashTuningConfig)

    @model_validator(mode="after")
    def _validate_intro_bounds(self) -> Self:
        if self.min_intro_seconds >= self.max_intro_seconds:
            raise ValueError(
                "min_intro_seconds must be strictly less than max_intro_seconds "
                f"(got {self.min_intro_seconds} >= {self.max_intro_seconds})"
            )
        return self


__all__ = [
    "ChromaprintTuningConfig",
    "FrameHashTuningConfig",
    "IntroDetectionAlgorithm",
    "IntroDetectionConfig",
]
