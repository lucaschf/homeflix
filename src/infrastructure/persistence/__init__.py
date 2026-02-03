"""Persistence layer for HomeFlix.

Contains SQLAlchemy ORM models, mappers, and repository implementations.
"""

from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.mappers import (
    EpisodeMapper,
    MovieMapper,
    SeasonMapper,
    SeriesMapper,
)
from src.infrastructure.persistence.models import (
    Base,
    EpisodeModel,
    MovieModel,
    SeasonModel,
    SeriesModel,
)
from src.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)

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
