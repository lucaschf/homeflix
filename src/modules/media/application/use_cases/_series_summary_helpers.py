"""Shared converters for ``SeriesSummaryOutput``.

Several use cases (``ListSeriesUseCase``, ``GetRelatedSeriesUseCase``,
future genre / search variants) build the same lightweight series
summary the catalog UI consumes. Keeping the converter in one place
avoids the inevitable drift where one site adds a new field and
others render an older shape.
"""

from src.modules.media.application.dtos.series_dtos import SeriesSummaryOutput
from src.modules.media.domain.entities.series import Series


def to_series_summary(series: Series, lang: str = "en") -> SeriesSummaryOutput:
    """Convert a ``Series`` entity to its catalog-card DTO."""
    return SeriesSummaryOutput(
        id=str(series.id),
        title=series.get_title(lang),
        start_year=series.start_year.value,
        end_year=series.end_year.value if series.end_year else None,
        is_ongoing=series.is_ongoing,
        synopsis=series.get_synopsis(lang),
        poster_path=series.poster_path.value if series.poster_path else None,
        backdrop_path=series.backdrop_path.value if series.backdrop_path else None,
        season_count=series.season_count,
        total_episodes=series.total_episodes,
        intro_marked_count=series.intro_marked_count,
        genres=series.get_genres(lang),
        library_id=series.library_id,
        tmdb_id=series.tmdb_id.value if series.tmdb_id else None,
        imdb_id=series.imdb_id.value if series.imdb_id else None,
    )


__all__ = ["to_series_summary"]
