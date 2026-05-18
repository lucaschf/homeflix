"""Collections event handlers."""

from src.modules.collections.application.event_handlers.on_movie_promoted_to_series import (
    OnMoviePromotedToSeriesHandler,
)
from src.modules.collections.application.event_handlers.on_user_deleted import (
    OnUserDeletedHandler,
)

__all__ = ["OnMoviePromotedToSeriesHandler", "OnUserDeletedHandler"]
