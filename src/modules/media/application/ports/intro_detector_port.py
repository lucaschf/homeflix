"""Port for detecting per-episode intro segments from audio fingerprints.

The intro-detection job feeds the port a season's worth of episode
fingerprints and receives, when convergence is reached, a marker per
episode pointing to the shared opening sequence. Implementations
(``ChromaprintIntroDetector``) live in the infrastructure layer; the
application uses only the abstraction so the algorithm can evolve
without touching the orchestrating use case.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.modules.media.domain.value_objects import EpisodeId


@dataclass(frozen=True)
class EpisodeFingerprint:
    """One episode's audio fingerprint, ready for cross-correlation.

    Attributes:
        episode_id: External id of the episode the fingerprint was
            computed for.
        hashes: Raw 32-bit Chromaprint fingerprint values, in the same
            order ``fpcalc`` emits them. The first hash corresponds to
            the start of the audio window analysed.
        duration_seconds: Length of audio that produced ``hashes``,
            as reported by fpcalc. Used to translate hash indices back
            to seconds without baking the Chromaprint hash rate into
            the port's contract.
    """

    episode_id: EpisodeId
    hashes: list[int]
    duration_seconds: float


@dataclass(frozen=True)
class DetectedIntro:
    """Result of running the detector against a single episode.

    Attributes:
        start_seconds: Offset from the start of the audio window where
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


class IntroDetectorPort(ABC):
    """Cross-correlate fingerprints to find a shared opening sequence."""

    @abstractmethod
    def detect(
        self, fingerprints: Sequence[EpisodeFingerprint]
    ) -> Mapping[EpisodeId, DetectedIntro]:
        """Return a marker per episode where detection converged.

        Implementations may return a partial map — episodes whose
        fingerprint did not align with enough peers are omitted rather
        than being given a low-confidence guess. The orchestrator
        treats a missing entry as "no intro detected for this episode".

        Args:
            fingerprints: One per episode in the season under analysis.
                Order is not significant; episodes are matched by id.

        Returns:
            A mapping keyed by episode id. May be empty when the season
            does not have enough episodes for cross-correlation, or when
            no shared segment crossed the implementation's confidence
            threshold.
        """
        ...


__all__ = ["DetectedIntro", "EpisodeFingerprint", "IntroDetectorPort"]
