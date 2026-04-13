"""Media type enum for watchable content."""

from enum import StrEnum


class WatchableMediaType(StrEnum):
    """Type of media that can have watch progress tracked.

    Attributes:
        MOVIE: A standalone movie.
        EPISODE: An episode within a series.

    Example:
        >>> WatchableMediaType.MOVIE
        'movie'
        >>> WatchableMediaType("episode") == "episode"
        True
    """

    MOVIE = "movie"
    EPISODE = "episode"


__all__ = ["WatchableMediaType"]
