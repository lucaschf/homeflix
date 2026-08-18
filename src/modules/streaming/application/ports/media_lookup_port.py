"""Cross-BC read port: resolve playback info for a media id (ADR-009).

The streaming context needs a physical file path (and the now-playing
display fields) for a movie or episode, but must not import the media
catalog aggregates directly. This port is the sanctioned seam: streaming
*defines* the contract it needs; the adapter that satisfies it lives in
``streaming/infrastructure/acl`` and reaches the catalog through media's
published use cases, preserving the per-profile library ACL.

The projections carry exactly the fields the stream routes consume — no
catalog entity crosses the boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class MoviePlaybackInfo:
    """Playback projection of a movie for the stream routes.

    Attributes:
        file_path: Absolute path to the primary video file, or ``None``
            when the movie has no playable file.
        scrub_preview_path: Absolute path to the scrub-preview VTT, or
            ``None`` when it has not been generated yet.
        title: Display title (for the now-playing row).
        year: Release year.
        resolution: Primary-file resolution label, or ``None``.
        poster_path: Poster image reference, or ``None``.
        duration_seconds: Runtime in seconds.
    """

    file_path: str | None
    scrub_preview_path: str | None
    title: str
    year: int
    resolution: str | None
    poster_path: str | None
    duration_seconds: int


@dataclass(frozen=True)
class EpisodePlaybackInfo:
    """Playback projection of a single episode for the stream routes.

    Attributes:
        episode_id: External id of the episode (``epi_xxx``), or ``None``.
        file_path: Absolute path to the primary video file, or ``None``.
        scrub_preview_path: Absolute path to the scrub-preview VTT, or
            ``None``.
        title: Episode title.
        duration_seconds: Runtime in seconds.
        segment_start_seconds: Start second of this episode within a
            shared physical file (ADR-030), or ``None`` for a whole file.
        segment_end_seconds: Exclusive end second within a shared file, or
            ``None``.
        series_title: Parent series display title (for the now-playing row).
    """

    episode_id: str | None
    file_path: str | None
    scrub_preview_path: str | None
    title: str
    duration_seconds: int
    segment_start_seconds: int | None
    segment_end_seconds: int | None
    series_title: str


class MediaPlaybackLookupPort(ABC):
    """Resolve playback info for a media id, honouring the profile ACL."""

    @abstractmethod
    async def find_movie(self, profile_id: str, movie_id: str) -> MoviePlaybackInfo:
        """Return playback info for a movie the profile may access.

        Args:
            profile_id: Caller's prefixed profile id — the catalog applies
                its per-profile library ACL against this.
            movie_id: External movie id (``mov_xxx``).

        Returns:
            The :class:`MoviePlaybackInfo` projection.

        Raises:
            ResourceNotFoundException: When the movie does not exist or the
                profile may not access its library — same behaviour the
                catalog use case surfaces, so the route still maps to 404.
        """
        ...

    @abstractmethod
    async def find_episode(
        self,
        profile_id: str,
        series_id: str,
        season_number: int,
        episode_number: int,
    ) -> EpisodePlaybackInfo | None:
        """Return playback info for one episode within a series.

        Args:
            profile_id: Caller's prefixed profile id (per-profile ACL).
            series_id: External series id (``ser_xxx``).
            season_number: 1-based season number.
            episode_number: 1-based episode number within the season.

        Returns:
            The :class:`EpisodePlaybackInfo` projection, or ``None`` when the
            series exists but has no such episode (the route maps that to
            404).

        Raises:
            ResourceNotFoundException: When the series does not exist or the
                profile may not access it.
        """
        ...


__all__ = [
    "EpisodePlaybackInfo",
    "MediaPlaybackLookupPort",
    "MoviePlaybackInfo",
]
