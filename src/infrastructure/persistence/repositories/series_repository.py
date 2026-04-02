"""SQLAlchemy series repository (re-export for backwards compatibility)."""

from src.modules.media.infrastructure.persistence.repositories.series_repository import (
    SQLAlchemySeriesRepository,
)

__all__ = ["SQLAlchemySeriesRepository"]
