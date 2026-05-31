"""Canonical media-type discriminator shared across bounded contexts (ADR-016)."""

from enum import StrEnum


class MediaType(StrEnum):
    """The kind of catalog title: a movie or a series.

    Canonical, project-wide discriminator for the "movie | series"
    concept (ADR-016). Lives in the shared kernel because media domain
    events carry it and other bounded contexts (catalog_requests,
    collections) consume it. Uses StrEnum so the value serializes
    directly as a string in DTOs and database columns.

    TMDB's ``"tv"`` vocabulary is NOT a member: it stays at the edge
    (TMDB DTOs/adapters) and is mapped to :attr:`SERIES` explicitly at
    the ACL. Playback granularity (``movie | episode``) is a different
    concept modelled by ``WatchableMediaType`` and is intentionally not
    unified here.

    Example:
        >>> MediaType.MOVIE.value
        'movie'
        >>> MediaType("series")
        <MediaType.SERIES: 'series'>
    """

    MOVIE = "movie"
    SERIES = "series"


# Back-compat alias — collections still imports ``CollectionMediaType``.
# Removed once collections migrates to ``MediaType`` (ADR-016, deferred).
CollectionMediaType = MediaType


__all__ = ["CollectionMediaType", "MediaType"]
