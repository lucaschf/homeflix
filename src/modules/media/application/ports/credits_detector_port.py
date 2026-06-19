"""Port for detecting the end-credits onset of a single media file.

Unlike intro detection (a season-scoped cross-correlation across
episodes), credits detection is **per-file**: each movie and each episode
is analysed independently for where its end credits begin. The contract
is therefore a single ``file_path`` in, an optional marker out.

The implementation (``CreditsDetector`` in the infrastructure layer) owns
its full pipeline — sampling the trailing window and scoring it with
complementary visual signals (edge/text density for bright rolling
credits, low frame-to-frame motion for static dark credits) — and
returns the highest-confidence onset, or ``None`` when no signal crosses
its internal floor (e.g. credits rolling over moving footage). The
orchestrating job applies the operator's ``min_confidence`` before
persisting, so the abstraction stays free of policy.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class CreditsSignal(StrEnum):
    """Which visual signal produced a detected credits onset.

    Recorded on the result so the orchestrator/observability can report
    *how* a marker was found — the two signals cover complementary
    content (see :class:`DetectedCredits`).

    Attributes:
        EDGE: Sustained high text/edge density — bright credits text
            (often scrolling) over a darker background. Typical of films.
        MOTION: Sustained low frame-to-frame motion — static or slowly
            changing credit cards. Typical of modern episodic credits,
            including dark productions where edge/brightness fail.
    """

    EDGE = "EDGE"
    MOTION = "MOTION"


@dataclass(frozen=True)
class CreditsDetectorTuning:
    """Operator-tunable knobs forwarded to the detector per call.

    Passed per ``detect()`` call so the implementation stays stateless
    with respect to runtime configuration — the credits-detection job
    snapshots ``RuntimeSettings`` and forwards the relevant fields,
    letting admin-panel edits take effect on the next tick.

    Attributes:
        analysis_window_seconds: How much *trailing* media (seconds) to
            sample. Credits can begin several minutes before the file
            ends (post-credit previews push them earlier), so this is
            generous by default.
        frame_sample_fps: Frames sampled per second within the window.
            Credits change slowly; 1 fps is plenty and keeps decode cheap.
        min_credits_seconds: Discard candidate regions shorter than this
            floor — guards against transient quiet beats or stray text.
        edge_rel_factor: Edge-density threshold as a multiple of the
            window's median, above which a frame counts as "text-heavy".
        motion_rel_factor: Motion threshold as a fraction of the window's
            median, below which a frame counts as "low activity".
    """

    analysis_window_seconds: int = 600
    frame_sample_fps: float = 1.0
    min_credits_seconds: float = 15.0
    edge_rel_factor: float = 1.3
    motion_rel_factor: float = 0.6


@dataclass(frozen=True)
class DetectedCredits:
    """Result of running the detector against a single media file.

    Attributes:
        start_seconds: Absolute offset from the start of the file where
            the end credits begin (the detector resolves the file
            duration to convert its trailing-window analysis into an
            absolute timestamp).
        confidence: ``[0.0, 1.0]`` — how strongly the winning signal
            stood out (depth of the motion valley / height of the edge
            shelf). The orchestrator applies a minimum threshold before
            persisting.
        signal: Which :class:`CreditsSignal` produced this onset.
    """

    start_seconds: float
    confidence: float
    signal: CreditsSignal


class CreditsDetectorPort(ABC):
    """Locate the end-credits onset of a single media file."""

    @abstractmethod
    def detect(self, file_path: str, tuning: CreditsDetectorTuning) -> DetectedCredits | None:
        """Analyse one file's trailing window for its credits onset.

        The implementation owns its full pipeline: sampling the trailing
        window, scoring it with each available signal, and returning the
        highest-confidence candidate. Returns ``None`` when the media
        cannot be read or no signal produces a sustained region — the
        caller treats that as "no credits detected" (the title's
        detection state becomes ``NO_CREDITS_FOUND``), never a guess.

        Args:
            file_path: Absolute path to the media file to analyse.
            tuning: Operator-tunable knobs for this call.

        Returns:
            A :class:`DetectedCredits`, or ``None`` when no confident
            onset was found.
        """
        ...


__all__ = [
    "CreditsDetectorPort",
    "CreditsDetectorTuning",
    "CreditsSignal",
    "DetectedCredits",
]
