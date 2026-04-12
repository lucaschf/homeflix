"""DTOs for the catalog search endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.building_blocks.application.pagination import DEFAULT_PAGE_SIZE


@dataclass(frozen=True)
class SearchInput:
    """Input for ``SearchCatalogUseCase``.

    Attributes:
        query: Full-text search string. Supports prefix matching
            (e.g. ``"incep"`` matches ``"Inception"``).
        media_type: Optional filter — restrict to ``"movie"`` or
            ``"series"``. ``None`` (default) searches both.
        genre: Optional canonical genre id filter.
        year_min: Optional inclusive lower bound on release year.
        year_max: Optional inclusive upper bound on release year.
        lang: Language for localized titles/synopses/genres.
        limit: Max results to return.
    """

    query: str
    media_type: Literal["movie", "series"] | None = None
    genre: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    lang: str = "en"
    limit: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True)
class SearchItemOutput:
    """One item in the search results.

    Same shape as ``CatalogItemOutput`` — reuses the same card
    component on the frontend.
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
class SearchOutput:
    """Output for ``SearchCatalogUseCase``.

    Attributes:
        items: Search results ordered by relevance.
        total: Total number of matching items (capped by the
            combined limit passed to both repositories).
    """

    items: list[SearchItemOutput]
    total: int


__all__ = [
    "SearchInput",
    "SearchItemOutput",
    "SearchOutput",
]
