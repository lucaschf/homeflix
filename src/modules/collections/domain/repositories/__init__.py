"""Collections repository interfaces."""

from src.modules.collections.domain.repositories.custom_list_repository import (
    CustomListRepository,
)
from src.modules.collections.domain.repositories.watchlist_repository import (
    WatchlistRepository,
)

__all__ = ["CustomListRepository", "WatchlistRepository"]
