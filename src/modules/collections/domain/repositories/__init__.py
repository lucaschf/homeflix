"""Collections repository interfaces."""

from src.modules.collections.domain.repositories.custom_list_repository import (
    CustomListRepository,
)
from src.modules.collections.domain.repositories.list_follow_repository import (
    ListFollowRepository,
)
from src.modules.collections.domain.repositories.watchlist_repository import (
    WatchlistCursor,
    WatchlistPage,
    WatchlistRepository,
)

__all__ = [
    "CustomListRepository",
    "ListFollowRepository",
    "WatchlistCursor",
    "WatchlistPage",
    "WatchlistRepository",
]
