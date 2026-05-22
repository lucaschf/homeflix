"""Intro detection tunables — Chromaprint detector calibration."""

from typing import Self

from pydantic import Field, model_validator

from src.building_blocks.domain.value_objects import CompoundValueObject


class IntroDetectionConfig(CompoundValueObject):
    """Operational knobs for the Chromaprint-based intro detector.

    Attributes:
        enabled: Toggle for the periodic intro-detection job. Requires
            the ``fpcalc`` binary on PATH; off by default.
        batch_size: Maximum number of seasons processed per detection
            tick. Each season triggers ffmpeg + fpcalc per episode, so
            values above 2 can saturate the host on large seasons.
        interval_minutes: How often the detection job runs.
        audio_window_seconds: Leading audio (in seconds) analysed per
            episode. 600s (10 min) covers all common cold-open + intro
            lengths; trimming this lower speeds up the job at the cost
            of missing intros that start late.
        min_confidence: Minimum detector confidence in ``[0.0, 1.0]``
            required before an auto-detected intro is persisted.
            Confidence is the fraction of peer episodes whose
            fingerprint agreed with the candidate marker.
        max_hash_hamming: Per-hash Hamming-distance ceiling (out of 32
            bits) considered a "match" between two episode
            fingerprints. Lower values reject more borderline hashes;
            higher values absorb more chromaprint noise.
        tolerance_hashes: How many CONSECUTIVE non-matching hashes a
            run can absorb before terminating. A fresh good hash
            resets the counter.
        min_intro_seconds: Minimum intro length to accept. Shorter
            matches are dropped (usually recurring stingers).
        max_intro_seconds: Hard cap on persisted intro length. Longer
            detections almost always include shared underscore that
            bleeds past the title sequence and are truncated.

    Example:
        >>> cfg = IntroDetectionConfig()
        >>> picky = cfg.with_updates(min_confidence=0.85, tolerance_hashes=1)
    """

    enabled: bool = Field(default=False)
    batch_size: int = Field(default=1, ge=1)
    interval_minutes: int = Field(default=30, ge=1)
    audio_window_seconds: int = Field(default=600, ge=60)
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    max_hash_hamming: int = Field(default=10, ge=0, le=32)
    tolerance_hashes: int = Field(default=2, ge=0)
    min_intro_seconds: float = Field(default=5.0, ge=0.0)
    max_intro_seconds: float = Field(default=120.0, ge=10.0)

    @model_validator(mode="after")
    def _validate_intro_bounds(self) -> Self:
        if self.min_intro_seconds >= self.max_intro_seconds:
            raise ValueError(
                "min_intro_seconds must be strictly less than max_intro_seconds "
                f"(got {self.min_intro_seconds} >= {self.max_intro_seconds})"
            )
        return self


__all__ = ["IntroDetectionConfig"]
