"""Featured media DTOs for the hero banner."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GetFeaturedInput:
    """Input for GetFeaturedMediaUseCase.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case
            consults ``ProfileLibraryAccessPort`` and restricts the
            random pool to libraries the profile may see; a deny-all
            profile yields an empty list without opening a UoW.
        media_type: Filter by type — "all", "movie", or "series".
        limit: Maximum number of items to return.
        lang: Language code for localized metadata.
    """

    profile_id: str
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
        logo_path: URL of the title-logo image (transparent PNG)
            populated from TMDB during enrich. Optional — only some
            titles have a logo on TMDB.
        content_rating: Age/content rating label, when known.
        trailer_url: Trailer URL, when known.
        matched_genres: Localized genres of this title that overlap the
            viewer's taste profile (their most-watched genres). Non-empty
            means the item was picked *because* of the viewer's history —
            the UI can render "because you watch Sci-Fi". Empty for random
            backfill and for viewers with no history.
    """

    id: str
    type: str
    title: str
    synopsis: str | None
    year: int
    duration_formatted: str | None
    genres: list[str]
    backdrop_path: str | None
    logo_path: str | None
    content_rating: str | None
    trailer_url: str | None
    matched_genres: list[str] = field(default_factory=list)
