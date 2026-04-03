"""Media domain entities."""

from src.modules.media.domain.entities.episode import Episode
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.entities.season import Season
from src.modules.media.domain.entities.series import Series

# Rebuild models to resolve forward references
Season.model_rebuild()
Series.model_rebuild()

__all__ = [
    "Episode",
    "Movie",
    "Season",
    "Series",
]
