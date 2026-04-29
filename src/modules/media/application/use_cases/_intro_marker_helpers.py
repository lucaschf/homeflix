"""Shared helpers for episode intro marker use cases."""

from src.modules.media.application.dtos.intro_dtos import IntroMarkerOutput
from src.modules.media.domain.value_objects import IntroMarker


def intro_marker_to_output(marker: IntroMarker) -> IntroMarkerOutput:
    """Convert a domain :class:`IntroMarker` to its output DTO.

    Single source of truth for the VO→DTO mapping. Use this from sites
    that already know the marker is present (e.g. the set use case).
    Sites that map ``episode.intro`` directly should call
    :func:`to_intro_marker_output` instead so they get the ``None`` →
    ``None`` passthrough.
    """
    return IntroMarkerOutput(
        start_seconds=marker.start_seconds,
        end_seconds=marker.end_seconds,
        source=marker.source.value,
        confidence=marker.confidence,
        detected_at=marker.detected_at.isoformat(),
    )


def to_intro_marker_output(marker: IntroMarker | None) -> IntroMarkerOutput | None:
    """Optional-aware variant of :func:`intro_marker_to_output`.

    Returns ``None`` when the episode has no marker so callers can pass
    ``episode.intro`` straight through without an explicit guard.
    """
    return None if marker is None else intro_marker_to_output(marker)


__all__ = ["intro_marker_to_output", "to_intro_marker_output"]
