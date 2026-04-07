"""Port for external metadata providers (TMDB, OMDb)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EpisodeMetadata:
    """Metadata for a single episode from an external provider.

    Attributes:
        season_number: Season number.
        episode_number: Episode number.
        title: Episode title.
        synopsis: Episode overview.
        air_date: Original air date (ISO format string).
        duration_seconds: Runtime in seconds.
    """

    season_number: int
    episode_number: int
    title: str | None = None
    synopsis: str | None = None
    air_date: str | None = None
    duration_seconds: int | None = None
    still_url: str | None = None


@dataclass(frozen=True)
class SeasonMetadata:
    """Metadata for a single season from an external provider.

    Attributes:
        season_number: Season number.
        title: Season title.
        synopsis: Season overview.
        poster_url: URL to season poster image.
        air_date: First air date (ISO format string).
        episodes: Episode metadata for this season.
    """

    season_number: int
    title: str | None = None
    synopsis: str | None = None
    poster_url: str | None = None
    air_date: str | None = None
    episodes: list[EpisodeMetadata] = field(default_factory=list)


@dataclass(frozen=True)
class CreditPerson:
    """A person involved in the production of a media item.

    Attributes:
        name: Full name.
        role: Role description (character name for cast, job title for crew).
        profile_url: URL to profile image.
        tmdb_id: TMDB person ID.
    """

    name: str
    role: str | None = None
    profile_url: str | None = None
    tmdb_id: int | None = None


@dataclass(frozen=True)
class LocalizedFields:
    """Localized metadata fields for a specific language.

    Attributes:
        title: Localized title.
        synopsis: Localized plot overview.
        genres: Localized genre names.
    """

    title: str | None = None
    synopsis: str | None = None
    genres: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MediaMetadata:
    """Metadata fetched from an external provider.

    Attributes:
        title: Official title.
        original_title: Original language title.
        year: Release year (movie) or start year (series).
        end_year: End year (series only, None if ongoing).
        duration_seconds: Runtime in seconds (movie only).
        synopsis: Plot overview.
        poster_url: URL to poster image.
        backdrop_url: URL to backdrop image.
        genres: List of genre names.
        tmdb_id: TMDB numeric ID.
        imdb_id: IMDb ID (tt1234567 format).
        seasons: Season metadata (series only).
        cast: Top billed actors.
        directors: Directors.
        writers: Screenwriters.
    """

    title: str
    original_title: str | None = None
    year: int | None = None
    end_year: int | None = None
    duration_seconds: int | None = None
    synopsis: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    genres: list[str] = field(default_factory=list)
    tmdb_id: int | None = None
    imdb_id: str | None = None
    seasons: list[SeasonMetadata] = field(default_factory=list)
    cast: list[CreditPerson] = field(default_factory=list)
    directors: list[CreditPerson] = field(default_factory=list)
    writers: list[CreditPerson] = field(default_factory=list)
    content_rating: str | None = None
    localized: dict[str, LocalizedFields] = field(default_factory=dict)


class MetadataProvider(ABC):
    """Port for fetching media metadata from external services."""

    @abstractmethod
    async def search_movie(self, title: str, year: int | None = None) -> MediaMetadata | None:
        """Search for a movie by title and optional year.

        Args:
            title: Movie title to search for.
            year: Release year to narrow results.

        Returns:
            Metadata for the best match, or None if not found.
        """
        ...

    @abstractmethod
    async def search_series(self, title: str, year: int | None = None) -> MediaMetadata | None:
        """Search for a TV series by title and optional year.

        Args:
            title: Series title to search for.
            year: Start year to narrow results.

        Returns:
            Metadata for the best match, or None if not found.
        """
        ...

    @abstractmethod
    async def get_movie_by_id(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch movie metadata by TMDB ID.

        Args:
            tmdb_id: The TMDB numeric ID.

        Returns:
            Movie metadata, or None if not found.
        """
        ...

    @abstractmethod
    async def get_series_by_id(self, tmdb_id: int) -> MediaMetadata | None:
        """Fetch series metadata by TMDB ID.

        Args:
            tmdb_id: The TMDB numeric ID.

        Returns:
            Series metadata with seasons and episodes, or None.
        """
        ...


__all__ = [
    "CreditPerson",
    "EpisodeMetadata",
    "MediaMetadata",
    "MetadataProvider",
    "SeasonMetadata",
]
