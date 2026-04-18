"""Shared helper for resolving per-library movie/series counts.

Centralizes the "ask the port for the two counts" call so each
use case reads as ``counts = await resolve_counts(entity, port)``
instead of inlining the pair of ``await`` calls at every site.
"""

from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.domain.entities.library import Library


async def resolve_counts(
    entity: Library,
    media_count_query: MediaCountQueryPort,
) -> tuple[int, int]:
    """Return ``(movie_count, series_count)`` for a library's paths."""
    paths = [p.value for p in entity.paths]
    movie_count = await media_count_query.count_movies_under_paths(paths)
    series_count = await media_count_query.count_series_under_paths(paths)
    return movie_count, series_count


__all__ = ["resolve_counts"]
