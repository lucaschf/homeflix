"""Shared quality projection for catalog rows.

``ListByGenreUseCase`` and ``ListRecentlyAddedCatalogUseCase`` both
build ``CatalogItemOutput`` from a ``Movie | Series`` and both need the
same quality pair the card badge renders. Keeping the derivation here
stops the two from drifting — a movie reads its own file variants while
a series has to reach through its episodes.
"""

from src.modules.media.domain.entities import Movie, Series


def catalog_quality(entity: Movie | Series) -> tuple[str | None, bool]:
    """Return the best resolution name and the HDR flag for a catalog row.

    Args:
        entity: The movie or series backing the row.

    Returns:
        A ``(resolution_name, has_hdr)`` pair. ``resolution_name`` is
        ``None`` when nothing behind the row has a file yet.
    """
    if isinstance(entity, Movie):
        best_file = entity.best_file
        return (best_file.resolution.value if best_file else None, entity.has_hdr)

    best_resolution = entity.best_resolution
    return (best_resolution.value if best_resolution else None, entity.has_hdr)


__all__ = ["catalog_quality"]
