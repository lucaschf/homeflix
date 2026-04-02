"""SQLAlchemy movie repository (re-export for backwards compatibility)."""

from src.modules.media.infrastructure.persistence.repositories.movie_repository import (
    SQLAlchemyMovieRepository,
)

__all__ = ["SQLAlchemyMovieRepository"]
