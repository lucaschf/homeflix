"""Shared helpers for episode intro marker use cases."""

from src.modules.media.application.dtos.intro_dtos import IntroMarkerOutput
from src.modules.media.domain.value_objects import IntroMarker


def to_intro_marker_output(marker: IntroMarker | None) -> IntroMarkerOutput | None:
    """Convert a domain :class:`IntroMarker` to its output DTO.

    Returns ``None`` when the episode has no marker so callers can pass
    ``episode.intro`` straight through without an explicit guard.
    """
    if marker is None:
        return None

    return IntroMarkerOutput(
        start_seconds=marker.start_seconds,
        end_seconds=marker.end_seconds,
        source=marker.source.value,
        confidence=marker.confidence,
        detected_at=marker.detected_at.isoformat(),
    )


__all__ = ["to_intro_marker_output"]
