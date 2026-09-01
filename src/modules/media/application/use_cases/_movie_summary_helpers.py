"""Shared converters for ``MovieSummaryOutput``.

Several use cases (``ListMoviesUseCase``, ``GetRelatedMoviesUseCase``,
future genre / search variants) build the same lightweight movie
summary the catalog UI consumes. Keeping the converter in one place
avoids the inevitable drift where one site adds a new field and
others render an older shape.
"""

from src.modules.media.application.dtos.movie_dtos import MovieSummaryOutput
from src.modules.media.domain.entities.movie import Movie


def to_movie_summary(movie: Movie, lang: str = "en") -> MovieSummaryOutput:
    """Convert a ``Movie`` entity to its catalog-card DTO."""
    best = movie.best_file
    return MovieSummaryOutput(
        id=str(movie.id),
        title=movie.get_title(lang),
        year=movie.year.value,
        duration_formatted=movie.duration.format_hms(),
        synopsis=movie.get_synopsis(lang),
        poster_path=movie.get_poster_path(lang),
        backdrop_path=movie.get_backdrop_path(lang),
        resolution=best.resolution.value if best else None,
        hdr=movie.has_hdr,
        variant_count=len(movie.files),
        available_resolutions=[r.value for r in movie.available_resolutions],
        genres=movie.get_genres(lang),
        library_id=movie.library_id,
        tmdb_id=movie.tmdb_id.value if movie.tmdb_id else None,
        imdb_id=movie.imdb_id.value if movie.imdb_id else None,
        needs_enrichment_review=movie.needs_enrichment_review,
    )


__all__ = ["to_movie_summary"]
