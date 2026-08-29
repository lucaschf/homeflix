"""Video frame-hash intro detector behind the port.

This adapter owns the full video pipeline for one season: for each
episode it samples + perceptually hashes the leading frames via
:class:`FrameHasher`, then hands the survivors to
:class:`FrameHashCorrelator` for diagonal-voting cross-correlation.
Episodes whose video cannot be decoded are dropped from the pool — the
detector is best-effort by design — and the count of successfully
analysed episodes is surfaced via :class:`IntroDetectionResult` so the
orchestrator can distinguish "nothing shared" from "not enough
material".

Unlike the audio detector, this approach matches the title sequence
regardless of how far a variable-length cold open pushed it — at the
cost of decoding video, which is heavier than fingerprinting audio.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.modules.media.application.ports.intro_detector_port import (
    IntroDetectionProgress,
    IntroDetectionResult,
    IntroDetectorPort,
    IntroDetectorTuning,
)
from src.modules.media.infrastructure.video.frame_hash_correlator import (
    FrameHashCorrelator,
    FrameHashTuning,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy as np

    from src.modules.media.application.ports.intro_detector_port import EpisodeMediaRef
    from src.modules.media.domain.value_objects import EpisodeId
    from src.modules.media.infrastructure.video.frame_hasher import FrameHasher

_logger = logging.getLogger(__name__)


class FrameHashIntroDetector(IntroDetectorPort):
    """Detect shared intros by cross-correlating per-frame perceptual hashes.

    Args:
        frame_hasher: ffmpeg-backed wrapper that samples + hashes an
            episode's leading frames.
        correlator: Pure diagonal-voting algorithm. Injected so it can
            be tuned (and stubbed in tests) independently of the I/O.

    Example:
        >>> detector = FrameHashIntroDetector(frame_hasher=hasher)
        >>> result = detector.detect(refs, FrameHashTuning())
    """

    def __init__(
        self,
        frame_hasher: FrameHasher,
        *,
        correlator: FrameHashCorrelator | None = None,
    ) -> None:
        self._frame_hasher = frame_hasher
        self._correlator = correlator or FrameHashCorrelator()

    def detect(
        self,
        episodes: Sequence[EpisodeMediaRef],
        tuning: IntroDetectorTuning,
        on_progress: IntroDetectionProgress | None = None,
    ) -> IntroDetectionResult:
        """Hash every episode's frames, then correlate the survivors.

        Decoding dominates the runtime, so ``on_progress`` fires after
        each episode — the correlation that follows is comparatively
        instant.
        """
        frame_tuning = _as_frame_hash_tuning(tuning)
        hashed: list[tuple[EpisodeId, np.ndarray]] = []
        total = len(episodes)
        for done, episode in enumerate(episodes, start=1):
            hashes = self._hash_one(episode, frame_tuning)
            if hashes is not None and len(hashes) > 0:
                hashed.append((episode.episode_id, hashes))
            if on_progress is not None:
                on_progress(done, total, episode.episode_id)
        markers = self._correlator.correlate(hashed, frame_tuning)
        return IntroDetectionResult(markers=markers, analyzed_count=len(hashed))

    def _hash_one(
        self,
        episode: EpisodeMediaRef,
        tuning: FrameHashTuning,
    ) -> np.ndarray | None:
        """Hash one episode's frames, swallowing any failure.

        Returns ``None`` when the video cannot be decoded (missing file,
        ffmpeg absent, unreadable codec) or the hasher crashes. A
        ``None`` just drops this episode from the pool — best-effort, so
        one bad episode never aborts the season.
        """
        try:
            return self._frame_hasher.hash_episode(
                episode.file_path,
                window_seconds=tuning.analysis_window_seconds,
                fps=tuning.frame_sample_fps,
            )
        except Exception:
            _logger.exception(
                "[intro-detection] frame hashing episode failed; skipping (%s)",
                episode.file_path,
            )
            return None


def _as_frame_hash_tuning(tuning: IntroDetectorTuning) -> FrameHashTuning:
    """Coerce the neutral tuning into the frame-hash subtype.

    The job builds a :class:`FrameHashTuning` directly, but the port
    signature is the neutral base; this keeps the adapter robust if a
    caller passes a plain :class:`IntroDetectorTuning` (falling back to
    the frame-hash defaults for the extra knobs).
    """
    if isinstance(tuning, FrameHashTuning):
        return tuning
    return FrameHashTuning(
        min_intro_seconds=tuning.min_intro_seconds,
        max_intro_seconds=tuning.max_intro_seconds,
        analysis_window_seconds=tuning.analysis_window_seconds,
    )


__all__ = ["FrameHashIntroDetector"]
