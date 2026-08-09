"""DTOs for the catalog (cross-cutting movies + series) endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.building_blocks.application.pagination import DEFAULT_PAGE_SIZE
from src.modules.media.domain.value_objects import CatalogSort

if TYPE_CHECKING:
    from src.shared_kernel.value_objects import MediaType


@dataclass(frozen=True)
class GenreOutput:
    """One row in the catalog genres listing.

    Attributes:
        id: Canonical English genre name. Stable across language
            switches and used as the filter key for
            ``GET /api/v1/catalog/by-genre/{id}``.
        name: Localized genre name for the requested ``lang``. Falls
            back to the canonical name when no translation exists.
        count: Total non-deleted movies + series tagged with this
            genre. Used by the frontend to sort the carousel order
            (most-populated genres first) and to suppress empty
            carousels.
    """

    id: str
    name: str
    count: int


@dataclass(frozen=True)
class ListGenresInput:
    """Input for ``ListGenresUseCase``.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case
            consults ``ProfileLibraryAccessPort`` and restricts the
            aggregation to libraries the profile may see; a deny-all
            profile yields an empty genre list without opening a UoW.
        lang: Language code used to resolve the localized display
            name for each canonical genre.
        media_type: Optional filter — when set to ``"movie"`` or
            ``"series"`` the use case only aggregates genres from
            the matching repository, so the resulting counts reflect
            that media type alone. ``None`` (default) aggregates both.
    """

    profile_id: str
    lang: str = "en"
    media_type: MediaType | None = None


@dataclass(frozen=True)
class ListGenresOutput:
    """Output for ``ListGenresUseCase``.

    Attributes:
        genres: All genres present in the library, sorted by count
            descending then alphabetically by display name.
    """

    genres: list[GenreOutput]


@dataclass(frozen=True)
class CatalogItemOutput:
    """One row in the catalog by-genre listing — movie or series.

    The ``type`` field discriminates so the frontend can render the
    right card variant and route to the right detail page.

    Attributes:
        id: External id (``mov_xxx`` or ``ser_xxx``) — the same id
            used by the existing detail endpoints.
        type: ``"movie"`` or ``"series"``.
        title: Localized title (or canonical when no translation).
        year: Release year for movies, start year for series.
        synopsis: Localized synopsis, or ``None``.
        poster_path: Poster URL or path, or ``None``.
        backdrop_path: Backdrop URL or path, or ``None``.
        genres: Localized genre list — same field as in the existing
            movie/series summaries so the frontend doesn't need a
            different card component.
    """

    id: str
    type: str
    title: str
    year: int
    synopsis: str | None
    poster_path: str | None
    backdrop_path: str | None
    genres: list[str]


@dataclass(frozen=True)
class ListByGenreInput:
    """Input for ``ListByGenreUseCase``.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case
            consults ``ProfileLibraryAccessPort`` and restricts both
            streams to libraries the profile may see; a deny-all
            profile yields an empty page without opening a UoW.
        genre: Canonical English genre id — same value the frontend
            received from ``ListGenresOutput.genres[*].id``.
        cursor: Opaque dual-stream cursor from the previous page, or
            ``None`` for the first page. A cursor minted under a
            different ``sort`` is rejected and treated as the first page.
        limit: Page size. Routes clamp to ``[1, MAX_PAGE_SIZE]``.
        lang: Language for localized titles / synopses / genres.
        media_type: Optional filter — when set the use case only
            pulls from the matching stream (movie or series). ``None``
            (default) merges both streams as usual.
        sort: Ordering for the merged listing (see :class:`CatalogSort`).
            Defaults to ``TITLE_ASC``.
    """

    profile_id: str
    genre: str
    cursor: str | None = None
    limit: int = DEFAULT_PAGE_SIZE
    lang: str = "en"
    media_type: MediaType | None = None
    sort: CatalogSort = CatalogSort.TITLE_ASC


@dataclass(frozen=True)
class ListByGenreOutput:
    """Output for ``ListByGenreUseCase``.

    Attributes:
        items: Mixed list of movies and series for the requested
            genre, ordered by the requested ``sort``.
        next_cursor: Opaque dual-stream cursor for the next page, or
            ``None`` when both streams are exhausted.
        has_more: Convenience flag matching ``next_cursor is not None``.
    """

    items: list[CatalogItemOutput]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class ListRecentlyAddedCatalogInput:
    """Input for ``ListRecentlyAddedCatalogUseCase``.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case
            consults ``ProfileLibraryAccessPort`` and restricts both
            streams to libraries the profile may see; a deny-all
            profile yields an empty list without opening a UoW.
        limit: Maximum number of mixed items to return. Routes clamp
            this to a sane upper bound before constructing the input.
        lang: Language code for localized titles, synopses, and genre
            names returned in each item.
    """

    profile_id: str
    limit: int = 20
    lang: str = "en"


@dataclass(frozen=True)
class ListRecentlyAddedCatalogOutput:
    """Output for ``ListRecentlyAddedCatalogUseCase``.

    Attributes:
        items: Mixed list of movies and series, newest first by
            ``created_at``. Same DTO shape as the by-genre / search
            responses so the frontend reuses the existing card.
    """

    items: list[CatalogItemOutput]


__all__ = [
    "CatalogItemOutput",
    "GenreOutput",
    "ListByGenreInput",
    "ListByGenreOutput",
    "ListGenresInput",
    "ListGenresOutput",
    "ListRecentlyAddedCatalogInput",
    "ListRecentlyAddedCatalogOutput",
]
