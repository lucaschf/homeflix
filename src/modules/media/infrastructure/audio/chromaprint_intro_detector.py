"""Audio-fingerprint intro detector (Chromaprint) behind the port.

This adapter owns the full audio pipeline for one season: for each
episode it extracts a leading audio window via ffmpeg, fingerprints it
with fpcalc, then hands the survivors to :class:`ChromaprintCorrelator`
for cross-correlation. Episodes whose audio cannot be read are dropped
from the pool — the detector is best-effort by design — and the count
of successfully analysed episodes is surfaced via
:class:`IntroDetectionResult` so the orchestrator can distinguish
"nothing shared" from "not enough material".

The pure correlation algorithm lives in
:mod:`chromaprint_correlator`; keeping extraction here and the algorithm
there means the algorithm stays unit-testable with synthetic
fingerprints, and this adapter stays a thin I/O shell.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.modules.media.application.ports.intro_detector_port import (
    IntroDetectionResult,
    IntroDetectorPort,
    IntroDetectorTuning,
)
from src.modules.media.infrastructure.audio.chromaprint_correlator import (
    ChromaprintCorrelator,
    ChromaprintTuning,
    EpisodeFingerprint,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.modules.media.application.ports.intro_detector_port import EpisodeMediaRef
    from src.modules.media.infrastructure.audio.audio_extractor import AudioExtractor
    from src.modules.media.infrastructure.audio.chromaprint_service import ChromaprintService

_logger = logging.getLogger(__name__)


class ChromaprintIntroDetector(IntroDetectorPort):
    """Detect shared intros by cross-correlating audio fingerprints.

    Args:
        audio_extractor: ffmpeg wrapper that produces a leading WAV
            window per episode.
        chromaprint_service: fpcalc wrapper that turns each WAV into a
            raw fingerprint.
        correlator: Pure cross-correlation algorithm. Injected so its
            algorithm-internal knobs can be tuned (and it can be
            stubbed in tests) independently of the I/O pipeline.

    Example:
        >>> detector = ChromaprintIntroDetector(
        ...     audio_extractor=extractor,
        ...     chromaprint_service=service,
        ... )
        >>> result = detector.detect(refs, ChromaprintTuning())
    """

    def __init__(
        self,
        audio_extractor: AudioExtractor,
        chromaprint_service: ChromaprintService,
        *,
        correlator: ChromaprintCorrelator | None = None,
    ) -> None:
        self._audio_extractor = audio_extractor
        self._chromaprint_service = chromaprint_service
        self._correlator = correlator or ChromaprintCorrelator()

    def detect(
        self,
        episodes: Sequence[EpisodeMediaRef],
        tuning: IntroDetectorTuning,
    ) -> IntroDetectionResult:
        """Fingerprint every episode, then correlate the survivors."""
        chroma_tuning = _as_chromaprint_tuning(tuning)
        fingerprints = self._fingerprint_all(episodes, chroma_tuning.analysis_window_seconds)
        markers = self._correlator.correlate(fingerprints, chroma_tuning)
        return IntroDetectionResult(markers=markers, analyzed_count=len(fingerprints))

    def _fingerprint_all(
        self,
        episodes: Sequence[EpisodeMediaRef],
        window_seconds: int,
    ) -> list[EpisodeFingerprint]:
        """Extract + fingerprint each episode, dropping the failures."""
        results: list[EpisodeFingerprint] = []
        for episode in episodes:
            fingerprint = self._fingerprint_one(episode, window_seconds)
            if fingerprint is not None:
                results.append(fingerprint)
        return results

    def _fingerprint_one(
        self,
        episode: EpisodeMediaRef,
        window_seconds: int,
    ) -> EpisodeFingerprint | None:
        """Run ffmpeg + fpcalc against a single episode.

        Returns ``None`` when any step degrades — missing primary file,
        ffmpeg or fpcalc absent, malformed output, or an unexpected
        crash in the audio stack. A ``None`` here just means this
        episode does not contribute to detection on this tick; the
        contract is best-effort so one bad episode never aborts the
        season.
        """
        try:
            with self._audio_extractor.extract_temporary(
                episode.file_path, duration_seconds=window_seconds
            ) as wav_path:
                if wav_path is None:
                    return None
                fingerprint = self._chromaprint_service.fingerprint(wav_path)
        except Exception:
            _logger.exception(
                "[intro-detection] fingerprinting episode failed; skipping (%s)",
                episode.file_path,
            )
            return None
        if fingerprint is None:
            return None
        return EpisodeFingerprint(
            episode_id=episode.episode_id,
            hashes=list(fingerprint.hashes),
            duration_seconds=fingerprint.duration_seconds,
        )


def _as_chromaprint_tuning(tuning: IntroDetectorTuning) -> ChromaprintTuning:
    """Coerce the neutral tuning into Chromaprint's calibrated subtype.

    The job builds a :class:`ChromaprintTuning` directly, but the port
    signature is the neutral base; this keeps the adapter robust if a
    caller passes a plain :class:`IntroDetectorTuning` (falling back to
    the Chromaprint defaults for the extra knobs).
    """
    if isinstance(tuning, ChromaprintTuning):
        return tuning
    return ChromaprintTuning(
        min_intro_seconds=tuning.min_intro_seconds,
        max_intro_seconds=tuning.max_intro_seconds,
        analysis_window_seconds=tuning.analysis_window_seconds,
    )


__all__ = ["ChromaprintIntroDetector"]
