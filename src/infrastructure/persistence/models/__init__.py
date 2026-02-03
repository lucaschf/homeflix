"""SQLAlchemy ORM models for HomeFlix.

All models inherit from Base and use external_id for API exposure.
"""

from src.infrastructure.persistence.models.base import Base
from src.infrastructure.persistence.models.episode import EpisodeModel
from src.infrastructure.persistence.models.movie import MovieModel
from src.infrastructure.persistence.models.season import SeasonModel
from src.infrastructure.persistence.models.series import SeriesModel

__all__ = [
    "Base",
    "EpisodeModel",
    "MovieModel",
    "SeasonModel",
    "SeriesModel",
]
