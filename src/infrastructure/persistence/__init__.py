"""Persistence layer for HomeFlix.

Contains SQLAlchemy ORM models, mappers, and repository implementations.
Module-specific components are re-exported via lazy imports.
"""

from typing import Any

from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.models.base import Base


def __getattr__(name: str) -> Any:
    """Lazy import module-specific components to avoid circular imports."""
    _mappers = {
        "EpisodeMapper": "src.modules.media.infrastructure.persistence.mappers.series_mapper",
        "MovieMapper": "src.modules.media.infrastructure.persistence.mappers.movie_mapper",
        "SeasonMapper": "src.modules.media.infrastructure.persistence.mappers.series_mapper",
        "SeriesMapper": "src.modules.media.infrastructure.persistence.mappers.series_mapper",
    }
    _models = {
        "EpisodeModel": "src.modules.media.infrastructure.persistence.models.episode",
        "MovieModel": "src.modules.media.infrastructure.persistence.models.movie",
        "SeasonModel": "src.modules.media.infrastructure.persistence.models.season",
        "SeriesModel": "src.modules.media.infrastructure.persistence.models.series",
    }
    _repos = {
        "SQLAlchemyMovieRepository": "src.modules.media.infrastructure.persistence.repositories.movie_repository",
        "SQLAlchemySeriesRepository": "src.modules.media.infrastructure.persistence.repositories.series_repository",
    }
    all_lazy = {**_mappers, **_models, **_repos}
    if name in all_lazy:
        import importlib

        module = importlib.import_module(all_lazy[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Database
    "Database",
    # Models
    "Base",
    "EpisodeModel",
    "MovieModel",
    "SeasonModel",
    "SeriesModel",
    # Mappers
    "EpisodeMapper",
    "MovieMapper",
    "SeasonMapper",
    "SeriesMapper",
    # Repositories
    "SQLAlchemyMovieRepository",
    "SQLAlchemySeriesRepository",
]
