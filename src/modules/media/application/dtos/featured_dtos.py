"""Featured media DTOs for the hero banner."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GetFeaturedInput:
    """Input for GetFeaturedMediaUseCase.

    Attributes:
        media_type: Filter by type — "all", "movie", or "series".
        limit: Maximum number of items to return.
        lang: Language code for localized metadata.
    """

    media_type: str = "all"
    limit: int = 6
    lang: str = "en"


@dataclass(frozen=True)
class FeaturedItemOutput:
    """A single featured media item for the hero banner.

    Attributes:
        id: External media ID.
        type: "movie" or "series".
        title: Localized display title.
        synopsis: Localized synopsis.
        year: Release year.
        duration_formatted: Duration string (movies only).
        genres: List of genre strings.
        backdrop_path: Path to backdrop image.
    """

    id: str
    type: str
    title: str
    synopsis: str | None
    year: int
    duration_formatted: str | None
    genres: list[str]
    backdrop_path: str | None
    content_rating: str | None
    trailer_url: str | None
