"""Movie DTOs for application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.building_blocks.application.pagination import DEFAULT_PAGE_SIZE

if TYPE_CHECKING:
    from src.modules.media.application.dtos.media_file_dtos import MediaFileOutput


@dataclass(frozen=True)
class GetMovieByIdInput:
    """Input for GetMovieByIdUseCase.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case looks
            up the per-profile library ACL through
            ``ProfileLibraryAccessPort`` and restricts the lookup to
            those libraries — a row outside the ACL surfaces as
            ``ResourceNotFoundException`` (404).
        movie_id: External ID of the movie (mov_xxx format).
        lang: Language code for localized metadata (e.g., "en", "pt-BR").
    """

    profile_id: str
    movie_id: str
    lang: str = "en"


@dataclass(frozen=True)
class DeleteMovieInput:
    """Input for DeleteMovieUseCase.

    Attributes:
        movie_id: External ID of the movie (mov_xxx format).
    """

    movie_id: str


@dataclass(frozen=True)
class CastMemberOutput:
    """Cast entry exposed on the API.

    Mirrors the domain ``CastMember`` shape so the detail UI can
    render an avatar (``profile_path``) + name + role per actor and
    deep-link to the actor's bio page via ``tmdb_id``.

    Attributes:
        name: Actor's display name.
        profile_path: Full URL to the TMDB profile photo, or ``None``
            when TMDB has no photo for this person — the UI falls
            back to an initials avatar.
        role: Character name played, or ``None`` when not provided.
        tmdb_id: TMDB person id, or ``None`` for rows enriched before
            the id was captured. The actor page uses this to fetch
            biography and birth date from ``/people/{id}``; absence
            degrades to a name-only header.
    """

    name: str
    profile_path: str | None
    role: str | None
    tmdb_id: int | None


@dataclass(frozen=True)
class CollectionOutput:
    """Collection (franchise) the movie belongs to.

    Attributes:
        tmdb_id: TMDB collection id.
        name: Display name (e.g. ``"Alien Collection"``).
        parts_count: Number of titles in the collection per TMDB.
    """

    tmdb_id: int
    name: str
    parts_count: int


@dataclass(frozen=True)
class MovieOutput:
    """Output representation of a Movie.

    Contains all movie fields serialized for API consumption.
    Value objects are converted to primitive types.

    Attributes:
        id: External movie ID (mov_xxx).
        title: Display title.
        original_title: Original language title (if different).
        year: Release year.
        duration_seconds: Duration in seconds.
        duration_formatted: Duration as HH:MM:SS.
        synopsis: Movie synopsis (optional).
        poster_path: Path to poster image (optional).
        backdrop_path: Path to backdrop image (optional).
        logo_path: URL of the title-logo image (transparent PNG)
            populated from TMDB during enrich, ``None`` if not
            available. Used by the hero/detail UI to render the title
            as a graphic.
        scrub_preview_path: Absolute filesystem path to the scrub-preview
            VTT, or ``None`` until the backfill job generates it.
        genres: List of genre strings.
        file_path: Path to video file (None if no primary file).
        file_size: File size in bytes (None if no primary file).
        resolution: Video resolution (None if no primary file).
        tmdb_id: TMDB external ID (optional).
        imdb_id: IMDB external ID (optional).
        created_at: ISO timestamp of creation.
        updated_at: ISO timestamp of last update.
    """

    id: str
    title: str
    original_title: str | None
    year: int
    duration_seconds: int
    duration_formatted: str
    synopsis: str | None
    tagline: str | None
    poster_path: str | None
    backdrop_path: str | None
    logo_path: str | None
    scrub_preview_path: str | None
    genres: list[str]
    cast: list[CastMemberOutput]
    directors: list[str]
    writers: list[str]
    content_rating: str | None
    trailer_url: str | None
    collection: CollectionOutput | None
    file_path: str | None
    file_size: int | None
    resolution: str | None
    files: list[MediaFileOutput]
    tmdb_id: int | None
    imdb_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MovieSummaryOutput:
    """Summary representation of a Movie for list views.

    Contains essential fields for displaying movies in a grid/list.

    Attributes:
        id: External movie ID.
        title: Display title.
        year: Release year.
        duration_formatted: Duration as HH:MM:SS.
        poster_path: Path to poster image (optional).
        resolution: Video resolution.
        genres: List of genre strings.
    """

    id: str
    title: str
    year: int
    duration_formatted: str
    synopsis: str | None
    poster_path: str | None
    backdrop_path: str | None
    resolution: str | None
    variant_count: int
    available_resolutions: list[str]
    genres: list[str]


@dataclass(frozen=True)
class ListMoviesInput:
    """Input for ListMoviesUseCase.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case
            consults ``ProfileLibraryAccessPort`` and restricts the
            page to libraries the profile may see; a deny-all profile
            yields an empty page without opening a UoW.
        cursor: Opaque pagination cursor from the previous page's
            ``next_cursor``. ``None`` (or any invalid token) starts at
            the first page.
        limit: Page size. Routes clamp this to ``[1, MAX_PAGE_SIZE]``
            before constructing the input.
        include_total: When ``True`` the use case asks the repository
            for an extra ``COUNT(*)`` so ``total_count`` is populated.
            Defaults to ``False`` because computing the total is the
            most expensive part of the query and is rarely needed by
            infinite-scroll consumers.
        lang: Language code for localized metadata.
    """

    profile_id: str
    cursor: str | None = None
    limit: int = DEFAULT_PAGE_SIZE
    include_total: bool = False
    lang: str = "en"


@dataclass(frozen=True)
class ListMoviesOutput:
    """Output for ListMoviesUseCase.

    Attributes:
        movies: List of movie summaries on this page.
        next_cursor: Opaque token to pass back as ``cursor`` on the
            next request, or ``None`` when there are no more pages.
        has_more: Convenience flag — equivalent to
            ``next_cursor is not None`` but explicit so clients don't
            have to infer it.
        total_count: Total number of (non-deleted) movies in the
            library, or ``None`` when the caller did not request it
            via ``include_total``.
    """

    movies: list[MovieSummaryOutput]
    next_cursor: str | None
    has_more: bool
    total_count: int | None = None


@dataclass(frozen=True)
class ListRecentlyAddedMoviesInput:
    """Input for ``ListRecentlyAddedMoviesUseCase``.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case
            consults ``ProfileLibraryAccessPort`` and restricts the
            top-N to libraries the profile may see; a deny-all
            profile yields an empty list without opening a UoW.
        limit: Maximum number of movies to return. Routes clamp this
            to a sane upper bound before constructing the input.
        lang: Language code for localized metadata.
    """

    profile_id: str
    limit: int = 20
    lang: str = "en"


@dataclass(frozen=True)
class ListRecentlyAddedMoviesOutput:
    """Output for ``ListRecentlyAddedMoviesUseCase``.

    Plain top-N projection — no cursor, no ``has_more``. The home-page
    carousel consumes the full slice in one shot and the user goes to
    the catalog page if they want to keep scrolling.

    Attributes:
        movies: List of movie summaries, newest first.
    """

    movies: list[MovieSummaryOutput]


__all__ = [
    "CollectionOutput",
    "GetMovieByIdInput",
    "ListMoviesInput",
    "ListMoviesOutput",
    "ListRecentlyAddedMoviesInput",
    "ListRecentlyAddedMoviesOutput",
    "MovieOutput",
    "MovieSummaryOutput",
]
