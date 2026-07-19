"""Column <-> ArtworkColumns conversion for the mirror finders (ADR-029).

Shared by the movie and series repositories so the raw poster/backdrop/
logo string columns are wrapped into (and unwrapped from) an
``ArtworkColumns`` value object in exactly one place.
"""

from __future__ import annotations

from src.modules.media.domain.value_objects import ArtworkColumns, ImageUrl


def to_artwork_columns(
    poster: str | None,
    backdrop: str | None,
    logo: str | None,
) -> ArtworkColumns:
    """Wrap raw column strings into an ``ArtworkColumns`` value object."""
    return ArtworkColumns(
        poster=ImageUrl(poster) if poster else None,
        backdrop=ImageUrl(backdrop) if backdrop else None,
        logo=ImageUrl(logo) if logo else None,
    )


def to_still_columns(thumbnail: str | None) -> ArtworkColumns:
    """Wrap a raw episode-still string into an ``ArtworkColumns`` (``still`` set)."""
    return ArtworkColumns(still=ImageUrl(thumbnail) if thumbnail else None)


def artwork_column_values(artwork: ArtworkColumns) -> dict[str, str | None]:
    """Unwrap an ``ArtworkColumns`` into a ``{column: value}`` update map."""
    return {
        "poster_path": artwork.poster.value if artwork.poster else None,
        "backdrop_path": artwork.backdrop.value if artwork.backdrop else None,
        "logo_path": artwork.logo.value if artwork.logo else None,
    }


__all__ = ["artwork_column_values", "to_artwork_columns", "to_still_columns"]
