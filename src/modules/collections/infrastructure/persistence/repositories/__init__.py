"""Collections repository implementations."""

from src.modules.collections.infrastructure.persistence.repositories.watchlist_repository import (
    SQLAlchemyWatchlistRepository,
)

__all__ = ["SQLAlchemyWatchlistRepository"]
