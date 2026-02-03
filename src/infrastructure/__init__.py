"""Infrastructure layer for HomeFlix.

Contains implementations of domain interfaces including:
- Database and ORM models
- Repository implementations
- External API clients
- File system services
"""

from src.infrastructure.persistence import (
    Base,
    Database,
    EpisodeMapper,
    EpisodeModel,
    MovieMapper,
    MovieModel,
    SeasonMapper,
    SeasonModel,
    SeriesMapper,
    SeriesModel,
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)

__all__ = [
    # Database
    "Database",
    "Base",
    # Models
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
