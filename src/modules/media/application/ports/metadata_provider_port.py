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
class PersonMetadata:
    """Biographical metadata for a single person fetched by id.

    Returned by ``MetadataProvider.get_person`` and surfaced by the
    actor page. Fields are deliberately a strict subset of TMDB's
    ``/person/{id}`` payload — only the ones the UI renders today —
    so adding fields later is additive at every layer.

    Attributes:
        tmdb_id: TMDB person ID.
        name: Display name.
        biography: Long-form biography text. Empty string when TMDB
            has no bio for this person; the UI hides the section then.
        birthday: ISO date (``YYYY-MM-DD``) or ``None`` when unknown /
            withheld.
        deathday: ISO date or ``None`` when alive / unknown.
        place_of_birth: Free-form string (e.g. ``"Los Angeles, California, USA"``)
            or ``None``.
        known_for_department: Primary department on TMDB
            (``"Acting"``, ``"Directing"``, etc.). ``None`` when not
            categorized.
        profile_path: Full URL to the profile image, or ``None``.
    """

    tmdb_id: int
    name: str
    biography: str = ""
    birthday: str | None = None
    deathday: str | None = None
    place_of_birth: str | None = None
    known_for_department: str | None = None
    profile_path: str | None = None


@dataclass(frozen=True)
class LocalizedFields:
    """Localized metadata fields for a specific language.

    Attributes:
        title: Localized title.
        synopsis: Localized plot overview.
        genres: Localized genre names.
        logo_url: Localized title-logo URL (transparent PNG). When
            present, the entity's ``get_logo_path(lang)`` accessor
            returns this in preference to the global ``logo_path``.
    """

    title: str | None = None
    synopsis: str | None = None
    tagline: str | None = None
    genres: list[str] = field(default_factory=list)
    logo_url: str | None = None


@dataclass(frozen=True)
class CollectionMetadata:
    """TMDB collection (franchise) metadata.

    Attributes:
        tmdb_id: TMDB collection id.
        name: Display name (e.g. ``"Alien Collection"``).
        parts_count: Number of titles in the collection per TMDB.
    """

    tmdb_id: int
    name: str
    parts_count: int


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
        logo_url: URL to title logo image (transparent PNG, no
            background) used by hero/detail UIs to render the title as
            a graphic. Optional — only some titles have logos in TMDB.
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
    logo_url: str | None = None
    genres: list[str] = field(default_factory=list)
    tmdb_id: int | None = None
    imdb_id: str | None = None
    seasons: list[SeasonMetadata] = field(default_factory=list)
    cast: list[CreditPerson] = field(default_factory=list)
    directors: list[CreditPerson] = field(default_factory=list)
    writers: list[CreditPerson] = field(default_factory=list)
    content_rating: str | None = None
    trailer_url: str | None = None
    tagline: str | None = None
    collection: CollectionMetadata | None = None
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

    @abstractmethod
    async def get_person(
        self,
        tmdb_id: int,
        language: str = "en-US",
    ) -> PersonMetadata | None:
        """Fetch biographical metadata for a person by id.

        Used by the actor page to render bio + birth date + known
        department alongside the catalog filmography. Returns ``None``
        when the provider has nothing for ``tmdb_id`` (deleted person,
        404, network error) — the actor page degrades gracefully and
        falls back to a name-only header.

        Args:
            tmdb_id: TMDB person id captured during movie enrichment.
            language: BCP-47 tag (e.g. ``"pt-BR"``, ``"en-US"``) for
                the localized bio. TMDB's coverage of non-English
                bios is uneven — implementations should fall back to
                English when the requested language returns an empty
                biography so the actor page never shows a blank
                section just because the translation is missing.

        Returns:
            ``PersonMetadata`` for the person, or ``None`` when the
            provider has no record / the call failed.
        """
        ...

    @abstractmethod
    async def get_movie_recommendations(self, tmdb_id: int) -> list[int]:
        """Return TMDB ids of movies recommended for ``tmdb_id``.

        Order matters: the first item is the most relevant recommendation
        according to the provider; callers preserve this order so the UI
        renders by descending relevance. Returns an empty list when the
        provider has no recommendations or the call fails — recommendation
        rendering is best-effort polish, never load-bearing.

        The returned ids are the *external provider* ids (TMDB person /
        movie ids); callers cross-reference them with their own catalog
        to filter to titles that actually exist locally.
        """
        ...

    @abstractmethod
    async def get_series_recommendations(self, tmdb_id: int) -> list[int]:
        """Return TMDB ids of series recommended for ``tmdb_id``.

        Mirrors :meth:`get_movie_recommendations` for the series catalog.
        Order matters: the first item is the most relevant recommendation
        according to the provider; callers preserve this order so the UI
        renders by descending relevance. Returns an empty list when the
        provider has no recommendations or the call fails — recommendation
        rendering is best-effort polish, never load-bearing.

        The returned ids are TMDB tv ids; callers cross-reference them
        with their own catalog to filter to series that actually exist
        locally.
        """
        ...


__all__ = [
    "CollectionMetadata",
    "CreditPerson",
    "EpisodeMetadata",
    "MediaMetadata",
    "MetadataProvider",
    "PersonMetadata",
    "SeasonMetadata",
]
