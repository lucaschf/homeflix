"""Port for detecting per-episode intro segments from episode media.

The intro-detection job hands the port a season's worth of episode
*file references* and receives, when convergence is reached, a marker
per episode pointing to the shared opening sequence. Each implementation
owns its full analysis pipeline (audio fingerprinting, video frame
hashing, …) behind this single abstraction, so the orchestrating job
never binds to a particular technique.

Implementations live in the infrastructure layer
(``ChromaprintIntroDetector``, ``FrameHashIntroDetector``); the
application uses only the abstraction so the algorithm can evolve — or
be swapped at runtime — without touching the job.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from src.modules.media.domain.value_objects import EpisodeId


@dataclass(frozen=True)
class EpisodeMediaRef:
    """A single episode's identity plus the media file to analyse.

    The port receives file references rather than pre-computed
    fingerprints so the analysis technique (audio vs. video) stays an
    implementation detail of the detector, not a leak in the contract.

    Attributes:
        episode_id: External id of the episode under analysis. Used to
            key the returned markers back to the episode.
        file_path: Absolute path to the episode's primary media file.
            The detector extracts whatever signal it needs (audio
            window, sampled frames) from this file.
    """

    episode_id: EpisodeId
    file_path: str


@dataclass(frozen=True)
class IntroDetectorTuning:
    """Operator-tunable knobs forwarded to the detector per call.

    Passed per ``detect()`` call so implementations stay stateless with
    respect to runtime configuration — the orchestrator (the
    intro-detection job) snapshots ``RuntimeSettings`` and forwards the
    relevant fields, letting admin-panel edits propagate to the next
    tick without re-constructing the detector.

    The base carries the algorithm-neutral bounds shared by every
    detector; technique-specific calibration (Hamming ceilings, frame
    sample rates, …) is added by per-algorithm subclasses so the port
    signature stays uniform.

    Attributes:
        min_intro_seconds: Discard matches shorter than this floor.
        max_intro_seconds: Hard cap on persisted match length.
        analysis_window_seconds: How much leading media (in seconds) the
            detector should analyse per episode. Covers the common
            cold-open + title-sequence span; trimming it speeds up
            analysis at the cost of missing late-starting intros.
    """

    min_intro_seconds: float = 5.0
    max_intro_seconds: float = 120.0
    analysis_window_seconds: int = 600


@dataclass(frozen=True)
class DetectedIntro:
    """Result of running the detector against a single episode.

    Attributes:
        start_seconds: Offset from the start of the analysed window where
            the shared intro begins.
        end_seconds: Offset where the intro ends. Always strictly
            greater than ``start_seconds``.
        confidence: ``[0.0, 1.0]`` — the share of pair-comparisons
            that agreed on this segment. The orchestrator can apply a
            minimum threshold before persisting.
    """

    start_seconds: float
    end_seconds: float
    confidence: float


@dataclass(frozen=True)
class IntroDetectionResult:
    """Outcome of a season-level detection run.

    Carries both the per-episode markers and how many episodes could
    actually be analysed, so the orchestrator can distinguish "analysed
    enough material but found no shared intro" (→ ``COMPLETED``) from
    "could not analyse enough episodes" (→ ``INSUFFICIENT_EPISODES``,
    which is retried on a later tick). Without ``analyzed_count`` a
    transient I/O failure — drive unmounted, file unreadable — would be
    silently flagged ``COMPLETED`` and never retried.

    Attributes:
        markers: One :class:`DetectedIntro` per episode where the
            detector converged. May be a partial map; a missing entry
            means "no intro detected for this episode".
        analyzed_count: How many episodes the detector successfully
            extracted signal from. Episodes whose media could not be
            read are excluded from this count.
    """

    markers: Mapping[EpisodeId, DetectedIntro]
    analyzed_count: int


IntroDetectionProgress = Callable[[int, int, EpisodeId], None]
"""Called once per episode as the detector works through the season.

Receives ``(done, total, episode_id)`` where ``done`` counts every
episode the detector has finished with — including ones it had to drop
— so the caller can render progress without knowing the pipeline.
Analysing a season is minutes-long work; without this the orchestrator
cannot tell "still decoding episode 3" from "wedged".
"""


class IntroDetectorPort(ABC):
    """Locate a season's shared opening sequence from episode media."""

    @abstractmethod
    def detect(
        self,
        episodes: Sequence[EpisodeMediaRef],
        tuning: IntroDetectorTuning,
        on_progress: IntroDetectionProgress | None = None,
    ) -> IntroDetectionResult:
        """Analyse a season's episodes and return one marker per match.

        Implementations own their full pipeline: extracting signal from
        each ``file_path``, dropping episodes whose media cannot be
        read, then cross-correlating the survivors. Episodes that did
        not align with enough peers are omitted from ``markers`` rather
        than given a low-confidence guess.

        Args:
            episodes: One reference per episode in the season under
                analysis. Order is not significant; episodes are keyed
                by id in the result.
            tuning: Operator-tunable knobs for this call. Allows
                admin-panel edits to take effect on the next tick
                without re-constructing the detector. Implementations
                may receive a technique-specific subclass.
            on_progress: Optional callback invoked after each episode is
                processed, so a caller can report progress during a long
                run. Implementations must tolerate ``None``.

        Returns:
            An :class:`IntroDetectionResult` whose ``markers`` may be
            empty when the season lacks enough analysable episodes, or
            when no shared segment crossed the implementation's
            confidence threshold.
        """
        ...


__all__ = [
    "DetectedIntro",
    "EpisodeMediaRef",
    "IntroDetectionProgress",
    "IntroDetectionResult",
    "IntroDetectorPort",
    "IntroDetectorTuning",
]
