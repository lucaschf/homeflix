"""DTOs for credits-marker use cases (movies + episodes)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SetCreditsMarkerInput:
    """Input for ``SetCreditsMarkerUseCase``.

    Manual edits always produce ``MANUAL``-source markers (no
    confidence). The duration-bound invariant
    (``start_seconds <= duration``) is enforced by the domain layer when
    the marker is applied to the movie/episode.

    Attributes:
        media_id: External id of the movie (mov_xxx) or episode (epi_xxx).
        start_seconds: Onset of the end credits, in seconds.
    """

    media_id: str
    start_seconds: int


@dataclass(frozen=True)
class CreditsMarkerOutput:
    """Output representation of a :class:`CreditsMarker`.

    Mirrors ``IntroMarkerOutput`` — reused both as the manual-edit
    response and embedded in the movie/episode read DTOs, so it carries
    no redundant media id.

    Attributes:
        start_seconds: Onset of the end credits, in seconds.
        source: ``"AUTO_DETECTED"`` or ``"MANUAL"``.
        confidence: Detection confidence in ``[0.0, 1.0]``; ``None`` for
            manual markers.
        detected_at: When the marker was produced or last edited (ISO 8601).
    """

    start_seconds: int
    source: str
    confidence: float | None
    detected_at: str


@dataclass(frozen=True)
class ResetCreditsDetectionInput:
    """Input for ``ResetCreditsDetectionUseCase``.

    Attributes:
        media_id: External id of the movie (mov_xxx) or episode (epi_xxx).
    """

    media_id: str


@dataclass(frozen=True)
class ResetCreditsDetectionOutput:
    """Outcome of requeuing a title for credits detection.

    Attributes:
        marker_cleared: ``True`` if an AUTO_DETECTED marker was removed.
            A MANUAL marker is preserved (the job skips it anyway).
    """

    marker_cleared: bool


__all__ = [
    "CreditsMarkerOutput",
    "ResetCreditsDetectionInput",
    "ResetCreditsDetectionOutput",
    "SetCreditsMarkerInput",
]
