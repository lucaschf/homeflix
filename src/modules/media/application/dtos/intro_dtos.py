"""DTOs for episode intro-marker use cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SetEpisodeIntroInput:
    """Input for ``SetEpisodeIntroUseCase``.

    Manual edits always produce ``MANUAL``-source markers — the use case
    never sets confidence (which is auto-detection only). Cross-field
    invariants (``end > start``, ``end <= episode.duration``) are
    enforced by the domain layer when the marker is applied to the
    episode.

    Attributes:
        episode_id: External id of the episode (epi_xxx).
        start_seconds: Offset from the start of the episode (seconds).
        end_seconds: Offset from the start of the episode (seconds).
    """

    episode_id: str
    start_seconds: int
    end_seconds: int


@dataclass(frozen=True)
class ClearEpisodeIntroInput:
    """Input for ``ClearEpisodeIntroUseCase``.

    Attributes:
        episode_id: External id of the episode (epi_xxx).
    """

    episode_id: str


@dataclass(frozen=True)
class ResetSeasonIntroDetectionInput:
    """Input for ``ResetSeasonIntroDetectionUseCase``.

    Attributes:
        season_id: External id of the season (ssn_xxx).
        run_now: Start detection for the season immediately instead of
            leaving it for the next scheduled tick. Off by default so
            the plain requeue keeps its original semantics.
    """

    season_id: str
    run_now: bool = False


@dataclass(frozen=True)
class ResetSeasonIntroDetectionOutput:
    """Outcome of resetting a season's intro detection.

    Attributes:
        markers_cleared: Auto-detected episode markers removed. MANUAL
            markers are preserved.
        detection_started: Whether a detection run was launched for the
            season right away. ``False`` when ``run_now`` was not asked
            for, or when a run for this season was already in flight.
    """

    markers_cleared: int
    detection_started: bool = False


@dataclass(frozen=True)
class IntroMarkerOutput:
    """Output representation of an :class:`IntroMarker`.

    Attributes:
        start_seconds: Offset from the start of the episode (seconds).
        end_seconds: Offset from the start of the episode (seconds).
        source: ``"AUTO_DETECTED"`` or ``"MANUAL"``.
        confidence: Detection confidence in ``[0.0, 1.0]``. ``None`` for
            manual markers.
        detected_at: When the marker was produced or last edited (ISO
            8601 UTC).
    """

    start_seconds: int
    end_seconds: int
    source: str
    confidence: float | None
    detected_at: str


__all__ = [
    "ClearEpisodeIntroInput",
    "IntroMarkerOutput",
    "ResetSeasonIntroDetectionInput",
    "ResetSeasonIntroDetectionOutput",
    "SetEpisodeIntroInput",
]
