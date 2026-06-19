"""Credits detection tunables — per-file detector knobs (ADR-014 bucket)."""

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class CreditsDetectionConfig(CompoundValueObject):
    """Operational knobs for the periodic credits-detection job (ADR-014).

    Credits detection is per-file (each movie/episode analysed
    independently), so unlike intro detection there is no algorithm
    selection: one combined detector runs both an edge/text-density and a
    low-motion signal and keeps the latest-onset candidate. The knobs
    here calibrate that single detector.

    Confidence is deliberately best-effort (credits onset is
    content-dependent), so ``min_confidence`` defaults low — the
    latest-onset selection and the ``min_credits_seconds`` floor already
    filter noise, and a manual editor backs up the misses. Raise it once
    the observability page shows the real confidence distribution.

    Attributes:
        enabled: Toggle for the periodic job. Off by default; requires
            ffmpeg + ffprobe on the host.
        batch_size: Max media files processed per detection tick. Each
            file decodes a trailing window, so keep this modest.
        interval_minutes: How often the detection job runs.
        analysis_window_seconds: Trailing media (seconds) sampled per
            file. Credits can begin minutes before the file ends, so this
            is generous; trimming speeds the job at the cost of missing
            early-starting credits.
        frame_sample_fps: Frames sampled per second. Credits change
            slowly; 1 fps is plenty and keeps decode cheap.
        min_confidence: Minimum detector confidence in ``[0.0, 1.0]``
            before an auto-detected marker is persisted.
        min_credits_seconds: Discard candidate regions shorter than this
            floor.
        edge_rel_factor: Edge-density threshold as a multiple of the
            window median (bright/scrolling credits signal).
        motion_rel_factor: Motion threshold as a fraction of the window
            median (static/dark credits signal).

    Example:
        >>> cfg = CreditsDetectionConfig()
        >>> picky = cfg.with_updates(min_confidence=0.7)
    """

    enabled: bool = Field(default=False)
    batch_size: int = Field(default=4, ge=1)
    interval_minutes: int = Field(default=30, ge=1)
    analysis_window_seconds: int = Field(default=600, ge=60)
    frame_sample_fps: float = Field(default=1.0, gt=0.0)
    min_confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    min_credits_seconds: float = Field(default=15.0, ge=1.0)
    edge_rel_factor: float = Field(default=1.3, gt=1.0)
    motion_rel_factor: float = Field(default=0.6, gt=0.0, lt=1.0)


__all__ = ["CreditsDetectionConfig"]
