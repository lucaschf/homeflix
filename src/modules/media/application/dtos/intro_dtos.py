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


__all__ = ["ClearEpisodeIntroInput", "IntroMarkerOutput", "SetEpisodeIntroInput"]
