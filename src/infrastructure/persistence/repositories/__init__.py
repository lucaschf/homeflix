"""SQLAlchemy repository implementations (re-export for backwards compatibility)."""

from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)

__all__ = [
    "SQLAlchemyMovieRepository",
    "SQLAlchemySeriesRepository",
]
