"""Shared helpers for credits-marker use cases (movie/episode dispatch).

Credits live on both movies and episodes (per-file detection), which sit
in different aggregates/repositories. These helpers parse a prefixed
media id, fetch/update the right one, and map the VO to its output DTO —
so the set/clear/reset use cases stay thin and free of the dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.credits_dtos import CreditsMarkerOutput
from src.modules.media.domain.value_objects import EpisodeId, MovieId, parse_media_id

if TYPE_CHECKING:
    from src.modules.media.application.unit_of_work import MediaUnitOfWork
    from src.modules.media.domain.entities import Episode, Movie
    from src.modules.media.domain.value_objects import CreditsDetectionState, CreditsMarker


def parse_creditable_id(media_id: str) -> MovieId | EpisodeId:
    """Parse ``media_id`` into a movie/episode id, or raise 404.

    Credits only apply to movies and episodes. A series/season id — or
    an unparseable string — is surfaced as a not-found creditable
    resource rather than a 500.
    """
    try:
        parsed = parse_media_id(media_id)
    except ValueError as exc:
        raise ResourceNotFoundException.for_resource("CreditableMedia", media_id) from exc
    if not isinstance(parsed, MovieId | EpisodeId):
        raise ResourceNotFoundException.for_resource("CreditableMedia", media_id)
    return parsed


async def fetch_creditable(
    uow: MediaUnitOfWork, media_id: MovieId | EpisodeId
) -> Movie | Episode | None:
    """Fetch the movie or episode the credits marker belongs to."""
    if isinstance(media_id, MovieId):
        return await uow.movies.find_by_id(media_id)
    return await uow.series.find_episode_by_id(media_id)


async def update_creditable_credits(
    uow: MediaUnitOfWork,
    media_id: MovieId | EpisodeId,
    marker: CreditsMarker | None,
    state: CreditsDetectionState,
) -> None:
    """Persist the marker + state on the right aggregate's row."""
    if isinstance(media_id, MovieId):
        await uow.movies.update_movie_credits(media_id, marker, state)
    else:
        await uow.series.update_episode_credits(media_id, marker, state)


def credits_marker_to_output(marker: CreditsMarker) -> CreditsMarkerOutput:
    """Convert a domain :class:`CreditsMarker` to its output DTO."""
    return CreditsMarkerOutput(
        start_seconds=marker.start_seconds,
        source=marker.source.value,
        confidence=marker.confidence,
        detected_at=marker.detected_at.isoformat(),
    )


def to_credits_marker_output(marker: CreditsMarker | None) -> CreditsMarkerOutput | None:
    """Optional-aware variant — ``None`` passthrough for embedding in reads."""
    return None if marker is None else credits_marker_to_output(marker)


__all__ = [
    "credits_marker_to_output",
    "fetch_creditable",
    "parse_creditable_id",
    "to_credits_marker_output",
    "update_creditable_credits",
]
