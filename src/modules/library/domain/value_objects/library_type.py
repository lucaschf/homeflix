"""Library type enumeration."""

from enum import StrEnum


class LibraryType(StrEnum):
    """Type of content a library contains.

    Determines how the scanner processes files and which metadata
    providers are most appropriate.

    Attributes:
        MOVIES: Library contains standalone films.
        SERIES: Library contains TV series with seasons and episodes.
        MIXED: Library contains both movies and series.

    Example:
        >>> lib_type = LibraryType.MOVIES
        >>> lib_type.value
        'movies'
        >>> LibraryType("series")
        <LibraryType.SERIES: 'series'>
    """

    MOVIES = "movies"
    SERIES = "series"
    MIXED = "mixed"


__all__ = ["LibraryType"]
