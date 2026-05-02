"""Type of media being requested."""

from enum import StrEnum


class RequestedMediaType(StrEnum):
    """The kind of TMDB title a catalog request points to.

    A request always targets a single TMDB resource — either a
    movie (``/movie/{id}``) or a TV series (``/tv/{id}``). The
    type controls how any future fulfillment lookup queries the
    local catalog (movie repository vs. series repository).

    Example:
        >>> RequestedMediaType.MOVIE
        <RequestedMediaType.MOVIE: 'movie'>
    """

    MOVIE = "movie"
    SERIES = "series"


__all__ = ["RequestedMediaType"]
