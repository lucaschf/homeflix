"""Media domain entities."""

from src.domain.media.entities.episode import Episode
from src.domain.media.entities.movie import Movie
from src.domain.media.entities.season import Season
from src.domain.media.entities.series import Series

# Rebuild models to resolve forward references
Season.model_rebuild()
Series.model_rebuild()

__all__ = [
    "Episode",
    "Movie",
    "Season",
    "Series",
]
