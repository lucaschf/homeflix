"""Media type enum for collections (watchlist, custom lists)."""

from enum import StrEnum


class CollectionMediaType(StrEnum):
    """Type of media that can be added to a collection.

    Uses StrEnum so the value serializes directly as a string
    in DTOs and database columns.

    Example:
        >>> CollectionMediaType.MOVIE.value
        'movie'
        >>> CollectionMediaType("series")
        <CollectionMediaType.SERIES: 'series'>
    """

    MOVIE = "movie"
    SERIES = "series"


__all__ = ["CollectionMediaType"]
